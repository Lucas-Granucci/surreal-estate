from html.parser import HTMLParser
from urllib.parse import urljoin

import pytest

from surreal_estate import cli
from surreal_estate.models import GroundingSupport
from surreal_estate.synthesis.dashboard import render_dashboard
from surreal_estate.synthesis.frontend import (
    build_frontend_response,
    load_snapshot_outcome,
    save_development_snapshot,
)
from surreal_estate.synthesis.viewer import TransientView
from test_frontend import outcome_fixture, request


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.hrefs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "a":
            self.hrefs.append(values.get("href", ""))


def test_dashboard_shows_original_recheck_and_preserves_source_indices():
    html = render_dashboard(build_frontend_response(outcome_fixture()))
    assert "PRIVATE-WEB" in html and "PRIVATE-CHECK" in html
    assert "Original search" in html and "Claim re-check" in html
    assert "not independently verified dossier evidence" in html
    assert "Source URL unavailable" in html
    assert 'href="#web-0-source-1">2</a>' in html
    assert 'id="web-0-source-0"' in html
    assert "friendly service" in html and "restaurants near property" in html
    assert "PRIVATE-DEBUG" not in html and "PRIVATE-TRACE" not in html
    links = Links(html)
    assert len(links.ids) == len(set(links.ids))
    assert all(href[1:] in links.ids for href in links.hrefs if href.startswith("#"))


def test_dashboard_escapes_untrusted_fields_and_sandboxes_provider_html():
    outcome = outcome_fixture()
    outcome.report.case.address = '<script>alert("address")</script>'
    outcome.displays[
        0
    ].response.text = '<script>alert("response")</script> [bad](javascript:alert(1))'
    outcome.displays[0].response.search_entry_point = '<script>alert("provider")</script>'
    outcome.displays[0].response.truncated = True
    outcome.displays[0].response.supports.append(
        GroundingSupport(text="Missing reference", chunk_indices=[-1, 500])
    )
    html = render_dashboard(build_frontend_response(outcome))
    assert "<script>" not in html
    assert 'href="javascript:' not in html
    assert "&lt;script&gt;" in html
    assert 'sandbox="allow-popups allow-popups-to-escape-sandbox"' in html
    assert "allow-scripts" not in html and "allow-same-origin" not in html
    assert "This response was truncated" in html
    assert "Unavailable (index -1)" in html and "Unavailable (index 500)" in html
    assert 'href="#web-0-source--1"' not in html


def test_empty_failed_and_demo_results_have_honest_states():
    outcome = outcome_fixture()
    outcome.report.demo = True
    outcome.displays = []
    outcome.report.result.coverage[0].status = "error"
    outcome.report.result.coverage[0].reason = "Search failed"
    html = render_dashboard(build_frontend_response(outcome))
    for message in [
        "Synthetic demo",
        "No supported observations yet",
        "No web response available",
        "No dossier evidence returned",
        "Search failed",
        "No validated research plan available",
    ]:
        assert message in html
    assert "0/1" in html


def test_dashboard_route_navigation_and_release():
    view = TransientView(outcome_fixture())
    base = "http://localhost/secret-token"
    for debug_path in ["/secret-token", "/secret-token/"]:
        headers, body = request(view, debug_path)
        assert b"200 OK" in headers
        dashboard_link = next(h for h in Links(body.decode()).hrefs if h.endswith("/dashboard"))
        assert urljoin(base, dashboard_link) == base + "/dashboard"
    headers, body = request(view, "/secret-token/dashboard")
    assert b"200 OK" in headers and b"Cache-Control: no-store" in headers
    assert b"default-src 'none'" in headers
    assert b"PRIVATE-WEB" in body
    for href in Links(body.decode()).hrefs:
        if href in ("./", "result.json"):
            path = urljoin(base + "/dashboard", href).replace("http://localhost", "")
            assert b"200 OK" in request(view, path)[0]
    assert b"404" in request(view, "/wrong-token/dashboard")[0]
    request(view, "/secret-token/release", "POST")
    assert view.dashboard is None
    assert b"410 Gone" in request(view, "/secret-token/dashboard")[0]


def test_dashboard_expiry_releases_all_buffers(monkeypatch):
    view = TransientView(outcome_fixture())
    monkeypatch.setattr("surreal_estate.synthesis.viewer.monotonic", lambda: view.expires_at + 1)
    headers, body = request(view, "/secret-token/dashboard")
    assert b"410 Gone" in headers and not body
    assert view.dashboard is None and view.html is None and view.json is None


def test_saved_snapshot_round_trip_and_view_command(tmp_path, monkeypatch):
    outcome = outcome_fixture()
    path = save_development_snapshot(outcome, str(tmp_path))
    restored = load_snapshot_outcome(str(path))
    assert build_frontend_response(restored) == build_frontend_response(outcome)
    assert restored.debug_events == []
    calls = []
    monkeypatch.setattr(cli, "serve", lambda result, port: calls.append((result, port)))
    monkeypatch.setattr("sys.argv", ["surreal-estate", "view", str(path), "--port", "0"])
    cli.main()
    assert len(calls) == 1 and calls[0][1] == 0
    assert calls[0][0].snapshot_path == str(path)


def test_view_rejects_invalid_snapshot_without_serving(tmp_path, monkeypatch):
    path = tmp_path / "invalid.json"
    path.write_text('{"report": {}}')
    monkeypatch.setattr("sys.argv", ["surreal-estate", "view", str(path)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
