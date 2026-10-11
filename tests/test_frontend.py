import json
from io import BytesIO
from types import SimpleNamespace

from surreal_estate.channels.web.channel import LiveDisplay
from surreal_estate.evals.fixtures import fixture_case
from surreal_estate.models import (
    ChannelResult,
    Coverage,
    GroundedResponse,
    GroundingChunk,
    GroundingSupport,
    RunReport,
)
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.orchestrator.runner import RunOutcome
from surreal_estate.store.export import build_export
from surreal_estate.store.sqlite import Store
from surreal_estate.synthesis.frontend import (
    DevelopmentSnapshot,
    FrontendResponse,
    build_frontend_response,
    save_development_snapshot,
)
from surreal_estate.synthesis.viewer import TransientView, display_handler, render_html


def outcome_fixture():
    response = GroundedResponse(
        provider="gemini_search",
        text="PRIVATE-WEB: reviews describe friendly service; this is opinion.",
        chunks=[GroundingChunk(), GroundingChunk(uri="https://example.org/review", title="Review")],
        supports=[
            GroundingSupport(
                text="friendly service", chunk_indices=[1], start_index=28, end_index=44
            )
        ],
        search_entry_point="<div>Search Suggestions</div>",
        search_queries=["restaurants near property"],
    )
    checked = response.model_copy(
        update={"text": "PRIVATE-CHECK: opinion retained; dates unresolved."}
    )
    ctx = RunContext()
    event = ctx.debug.begin("debug", {"private": "PRIVATE-DEBUG"})
    ctx.debug.finish(event)
    return RunOutcome(
        RunReport(
            case=fixture_case(),
            result=ChannelResult(
                coverage=[
                    Coverage(
                        channel="web",
                        topic="restaurant_reviews",
                        status="complete",
                        reason="Search completed",
                    )
                ]
            ),
            trace=["PRIVATE-TRACE"],
        ),
        [
            LiveDisplay(response, "restaurant_reviews"),
            LiveDisplay(checked, "restaurant_reviews", "Claim re-check · model assessment"),
        ],
        ctx.debug.events,
    )


def test_frontend_preserves_original_recheck_and_citation_positions():
    outcome = outcome_fixture()
    payload = build_frontend_response(outcome)
    loaded = FrontendResponse.model_validate_json(payload.model_dump_json())
    assert loaded.purpose == "user_display" and loaded.retention == "ephemeral"
    assert loaded.report.id == outcome.report.id
    assert len(loaded.web) == 2
    assert loaded.web[0].response == outcome.displays[0].response
    assert loaded.web[1].response == outcome.displays[1].response
    assert loaded.web[0].response.chunks[0].uri is None
    assert loaded.web[0].response.supports[0].chunk_indices == [1]
    assert loaded.web[0].label == "model_reported_summary"
    assert loaded.web[1].label == "model_assessment"
    assert loaded.report.result.coverage[0].status == "complete"
    assert "PRIVATE-DEBUG" not in payload.model_dump_json()
    assert "PRIVATE-TRACE" not in payload.model_dump_json()


class FakeSocket:
    def __init__(self, request):
        self.request = BytesIO(request)
        self.response = bytearray()

    def makefile(self, *args):
        return self.request

    def sendall(self, data):
        self.response.extend(data)


def request(view, path, method="GET"):
    socket = FakeSocket(f"{method} {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
    display_handler(view, "secret-token")(socket, ("127.0.0.1", 1234), SimpleNamespace())
    return bytes(socket.response).split(b"\r\n\r\n", 1)


def test_json_http_access_release_and_no_store_headers():
    view = TransientView(outcome_fixture())
    headers, body = request(view, "/secret-token/result.json")
    assert b"200 OK" in headers and b"application/json" in headers
    assert b"Cache-Control: no-store" in headers
    assert b"Access-Control-Allow-Origin" not in headers
    assert len(json.loads(body)["web"]) == 2
    assert b'\n  "web": [\n' in body
    assert request(view, "/wrong-token/result.json")[0].startswith(b"HTTP/1.0 404")
    assert request(view, "/wrong-token/release", "POST")[0].startswith(b"HTTP/1.0 404")
    assert view.active
    assert request(view, "/secret-token/release", "POST")[0].startswith(b"HTTP/1.0 204")
    assert view.html is None and view.json is None
    assert request(view, "/secret-token/result.json")[0].startswith(b"HTTP/1.0 410")


def test_expiry_clears_buffers_before_serving(monkeypatch):
    view = TransientView(outcome_fixture())
    monkeypatch.setattr("surreal_estate.synthesis.viewer.monotonic", lambda: view.expires_at + 1)
    headers, body = request(view, "/secret-token/result.json")
    assert b"410 Gone" in headers and not body
    assert view.html is None and view.json is None


def test_dashboard_displays_indented_json_with_escaped_provider_text():
    outcome = outcome_fixture()
    outcome.displays[0].response.text = "<script>untrusted()</script>"
    html = render_html(outcome)
    assert "View full JSON" in html and "id='frontend-json'" in html
    assert "\n  &quot;web&quot;: [\n" in html
    assert "PRIVATE-CHECK" in html
    assert "&lt;script&gt;untrusted()&lt;/script&gt;" in html
    assert "<script>untrusted()" not in html


def test_transient_web_still_excluded_from_disk_and_sqlite(tmp_path):
    outcome = outcome_fixture()
    policy = RunContext().policy
    assert "PRIVATE-WEB" in build_frontend_response(outcome).model_dump_json()
    assert "PRIVATE-WEB" not in build_export(outcome.report, policy).model_dump_json()
    store = Store(str(tmp_path / "run.db"))
    try:
        store.save(outcome.report, policy)
        assert "PRIVATE" not in store.load(outcome.report.id).model_dump_json()
    finally:
        store.close()


def test_development_snapshot_keeps_both_web_responses_after_view_release(tmp_path):
    outcome = outcome_fixture()
    path = save_development_snapshot(outcome, str(tmp_path / "exports"))
    view = TransientView(outcome)
    view.release()
    loaded = DevelopmentSnapshot.model_validate_json(path.read_text())
    assert path.name == outcome.report.id + ".json"
    assert loaded.retention == "development_file"
    assert loaded.purpose == "development_debug"
    assert loaded.web[0].response == outcome.displays[0].response
    assert loaded.web[1].response == outcome.displays[1].response
    assert "PRIVATE-DEBUG" not in path.read_text()
