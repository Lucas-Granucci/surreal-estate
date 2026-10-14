import asyncio
import json
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from surreal_estate import cli
from surreal_estate.evals.fixtures import FixtureAPI, FixturePlanner, FixtureSearch, fixture_case
from surreal_estate.models import ChannelResult, Coverage
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.orchestrator.runner import run
from surreal_estate.webapp.server import AddressRequest, App, ResearchRequest, app_handler, research
from test_frontend import FakeSocket, outcome_fixture


def request(app, path, *, method="GET", payload=None, token=True, host="localhost:8765", origin=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    headers = f"{method} {path} HTTP/1.0\r\nHost: {host}\r\nContent-Length: {len(body)}\r\n"
    if token:
        headers += f"X-CSRF-Token: {app.csrf}\r\n"
    if origin:
        headers += f"Origin: {origin}\r\n"
    sock = FakeSocket(headers.encode() + b"\r\n" + body)
    app_handler(app)(sock, ("127.0.0.1", 1234), SimpleNamespace(server_port=8765))
    return bytes(sock.response).split(b"\r\n\r\n", 1)


def wait_for_job(app, identifier):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = app.get(identifier)
        if job["status"] != "running":
            return job
        time.sleep(.005)
    pytest.fail("Research job did not finish")


MATCH = {"matchedAddress": "414 GRANT ST, PITTSBURGH, PA, 15219",
         "coordinates": {"y": 40.438, "x": -79.997},
         "addressComponents": {"city": "PITTSBURGH", "state": "PA"}}


async def fixture_resolver(request):
    return [MATCH], "https://geocoding.geo.census.gov/result"


def confirmed_request(app):
    app.resolver = fixture_resolver
    result = app.geocode(AddressRequest(address="414 Grant Street"))
    return ResearchRequest(address="414 Grant Street", channels=["apis"],
                           confirmation=result["candidates"][0]["confirmation"])


async def fixture_executor(request, ctx):
    return outcome_fixture()


def test_start_poll_save_restart_and_open_complete_report(tmp_path):
    app = App(tmp_path, fixture_executor)
    headers, body = request(app, "/api/runs", method="POST", payload=confirmed_request(app).model_dump())
    assert b"202 Accepted" in headers
    identifier = json.loads(body)["id"]
    assert wait_for_job(app, identifier)["status"] == "complete"
    # A new app instance reloads history and report data without provider calls.
    restored = App(tmp_path, fixture_executor)
    headers, body = request(restored, "/api/runs")
    assert json.loads(body)["runs"][0]["id"] == identifier
    for page, expected in [("dashboard", b"app.js"), ("bench.json", b"PRIVATE-WEB"), ("result.json", b"PRIVATE-CHECK"), ("debug", b"dashboard")]:
        headers, body = request(restored, f"/reports/{identifier}/{page}")
        assert b"200 OK" in headers and b"Cache-Control: no-store" in headers
        assert expected in body
        assert b"PRIVATE-DEBUG" not in body
    _, dashboard = request(restored, f"/reports/{identifier}/dashboard")
    assert b'data-action="home"' in dashboard and b'href="debug"' not in dashboard
    assert b"expires after" not in dashboard
    assert b'aria-label="Main"' in dashboard


def test_interrupted_job_is_recovered_as_failed(tmp_path):
    identifier = str(uuid4())
    path = tmp_path / f"job-{identifier}.json"
    path.write_text(json.dumps(dict(id=identifier, status="running", address="414 Grant Street", created_at="2026-10-12")))
    app = App(tmp_path)
    assert app.get(identifier)["status"] == "failed"
    assert "stopped" in app.get(identifier)["message"]
    assert json.loads(path.read_text())["status"] == "failed"


def test_provider_error_does_not_leak_secrets_and_can_retry(tmp_path):
    async def failed(*args):
        raise RuntimeError("SECRET_TOKEN=do-not-display")
    app = App(tmp_path, failed)
    job = app.start(confirmed_request(app))
    assert wait_for_job(app, job["id"])["status"] == "failed"
    _, body = request(app, "/api/runs")
    assert b"SECRET_TOKEN" not in body
    app.executor = fixture_executor
    retry = app.start(confirmed_request(app))
    assert wait_for_job(app, retry["id"])["status"] == "complete"


def test_only_one_run_at_a_time(tmp_path):
    gate = threading.Event()
    async def slow(*args):
        await asyncio.to_thread(gate.wait, 2)
        return outcome_fixture()
    app = App(tmp_path, slow)
    job = app.start(confirmed_request(app))
    try:
        headers, _ = request(app, "/api/runs", method="POST", payload={"address": "414 Grant Street", "channels": ["apis"]})
        assert b"409 Conflict" in headers
    finally:
        gate.set()
        wait_for_job(app, job["id"])


@pytest.mark.parametrize("payload", [
    {"address": "   ", "channels": ["apis"]},
    {"address": "      ", "channels": ["apis"]},
    {"address": "414 Grant Street", "channels": []},
    {"address": "414 Grant Street", "channels": ["listing"]},
    {"address": "414 Grant Street", "channels": ["web"], "topics": []},
    {"address": "414 Grant Street", "channels": ["apis", "apis"]},
])
def test_invalid_input_never_starts_research(tmp_path, payload):
    app = App(tmp_path, fixture_executor)
    headers, _ = request(app, "/api/runs", method="POST", payload=payload)
    assert b"400 Bad Request" in headers and not app.jobs


@pytest.mark.parametrize("kwargs", [{"token": False}, {"host": "attacker.example:8765"}, {"origin": "https://attacker.example"}])
def test_foreign_requests_cannot_start_research(tmp_path, kwargs):
    app = App(tmp_path, fixture_executor)
    headers, _ = request(app, "/api/runs", method="POST", payload={"address": "414 Grant Street", "channels": ["apis"]}, **kwargs)
    assert b"403 Forbidden" in headers and not app.jobs


def test_assets_and_unknown_paths(tmp_path):
    app = App(tmp_path)
    for path, kind in [("/", b"text/html"), ("/app.js", b"text/javascript"), ("/app.css", b"text/css")]:
        headers, body = request(app, path)
        assert b"200 OK" in headers and kind in headers and body
    for path in ["/reports/../../.env", "/.env", "/api/runs/unknown", "/reports/unknown/dashboard"]:
        assert b"404 Not Found" in request(app, path)[0]
    assert b"403 Forbidden" in request(app, "/api/runs", host="evil.test")[0]


async def test_selected_web_channel_does_not_run_default_structured_channel():
    class NeverAPI:
        default_enabled = True
        async def run(self, *args):
            pytest.fail("Deselected structured channel must never execute")
    class DisplaySearch(FixtureSearch):
        async def search(self, *args):
            response = await super().search(*args)
            return response.model_copy(update={"provider": "gemini_search", "search_entry_point": "<div>Suggestions</div>"})
    result = await run(fixture_case(), RunContext(), FixturePlanner(), NeverAPI(), search=DisplaySearch(), selected_channels=["web"])
    assert result.report.plan.channels == ["web"]
    assert result.displays
    assert all(c.reason == "Not selected for this run" for c in result.report.result.coverage if c.channel == "apis")


async def test_selected_structured_channel_runs_once_and_does_not_search():
    class CountingAPI(FixtureAPI):
        default_enabled = True
        calls = 0
        async def run(self, *args):
            self.calls += 1
            return ChannelResult(coverage=[Coverage(channel="apis", topic="geocoding", status="complete", reason="Done")])
    class NeverSearch:
        async def search(self, *args):
            pytest.fail("Deselected web channel must never execute")
    api = CountingAPI()
    result = await run(fixture_case(), RunContext(), FixturePlanner(), api, search=NeverSearch(), selected_channels=["apis"])
    assert result.report.plan.channels == ["apis"]
    assert result.report.plan.queries == [] and api.calls == 1
    assert result.displays == []


async def test_webapp_scope_reaches_cli_and_demo_is_offline(monkeypatch):
    calls = []
    async def execute(args, *, ctx):
        calls.append(args)
        return outcome_fixture()
    monkeypatch.setattr(cli, "execute", execute)
    await research(ResearchRequest(address="414 Grant Street", channels=["apis"], topics=["restaurant_reviews"]), RunContext())
    assert calls[0].topic == [] and not calls[0].web and not calls[0].save_json
    await research(ResearchRequest(address="414 Grant Street", channels=["apis"], demo=True), RunContext())
    assert calls[1].command == "demo"


def test_app_cli_starts_server(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("surreal_estate.webapp.server.serve_app", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr("sys.argv", ["surreal-estate", "app", "--port", "0", "--data-dir", str(tmp_path)])
    cli.main()
    assert calls == [{"port": 0, "directory": str(tmp_path)}]


def test_report_visuals_use_real_coordinates_dates_and_escape_names():
    from datetime import date
    from surreal_estate.models import Evidence
    from surreal_estate.synthesis.report_visuals import nearby_map, closure_timeline

    def evidence(provider, **details):
        return Evidence(provider=provider, uri="https://example.org/source", title="Permit <unsafe>", excerpt="Source", retention="persistent", kind="official_record", details=details)

    location = evidence("census", latitude=40.0, longitude=-80.0)
    places = evidence("openstreetmap", category="groceries", mapped_feature_count=1,
                      count_is_lower_bound=True, members=[dict(name="<script>evil</script>",
                      center=dict(lat=40.001, lon=-80.0), approximate_center_distance_m=111,
                      object_type="node", object_id=42)])
    html = nearby_map([location, places], interactive=True)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'href="https://www.openstreetmap.org/node/42"' in html
    assert '1+</strong>' in html and 'data-map-select="groceries"' in html
    assert 'cy="-16.59"' in html
    assert nearby_map([places]) == ""
    closure = evidence("wprdc", record=dict(closure_id="A", from_date="2026-10-01", to_date="2026-10-31"))
    html = closure_timeline([closure], date(2026, 10, 12))
    assert 'width:100.00%' in html and '2026-10-01 to 2026-10-31' in html
    assert 'Permit &lt;unsafe&gt;' in html and 'do not confirm crews' in html
    closure.details["record"]["to_date"] = "unknown"
    assert closure_timeline([closure], date(2026, 10, 12)) == ""


def test_map_draws_real_closure_geometry_and_ignores_malformed_segments():
    from surreal_estate.models import Evidence
    from surreal_estate.synthesis.report_visuals import nearby_map

    def item(provider, **details):
        return Evidence(provider=provider, uri="https://example.org/source", title="Closure <unsafe>", excerpt="Record", retention="persistent", kind="official_record", details=details)

    location = item("census", latitude=40.0, longitude=-80.0)
    places = item("openstreetmap", category="transit", members=[dict(name="Stop", object_type="node", object_id=123, center=dict(lat=40.0001, lon=-80.0))])
    closure = item("wprdc_closures", record=dict(geometry="[[40.0,-80.0],[40.001,-80.0]]"))
    html = nearby_map([location, places, closure], interactive=True)
    assert 'class="closure-path" points="0.00,-0.00 0.00,-16.59"' in html
    assert "Dotted red lines" in html and "Closure &lt;unsafe&gt;" in html
    assert 'aria-pressed="true"' in html and 'data-map-list="transit" open' in html
    assert 'clip-path="url(#nearby-map-clip)"' in html
    for bad in ["not json", [[999, 0], [1, 2]], {"lat": 40}, [[40, -80], ["NaN", 0]]]:
        closure.details["record"]["geometry"] = bad
        assert "closure-path" not in nearby_map([location, places, closure])


async def test_selected_parcel_reaches_research_case(monkeypatch):
    calls = []
    async def execute(args, *, ctx):
        calls.append(args)
        return outcome_fixture()
    monkeypatch.setattr(cli, "execute", execute)
    await research(ResearchRequest(address="414 Grant Street", channels=["apis"], parcel_id="0002J00002000000"), RunContext())
    assert calls[0].parcel_id == "0002J00002000000"
    assert calls[0].web is False


def test_confirmation_required_and_bound_to_address(tmp_path):
    app = App(tmp_path, fixture_executor, fixture_resolver)
    payload = {"address": "414 Grant Street", "channels": ["apis"]}
    headers, _ = request(app, "/api/runs", method="POST", payload=payload)
    assert b"409 Conflict" in headers and not app.jobs
    confirmed = confirmed_request(app)
    confirmed.address = "416 Grant Street"
    with pytest.raises(RuntimeError, match="confirm"):
        app.start(confirmed)
    confirmed.address = "414 Grant Street"
    confirmed.geography = "Boston, Massachusetts"
    with pytest.raises(RuntimeError, match="confirm"):
        app.start(confirmed)
    confirmed.geography = "Pittsburgh, Pennsylvania"
    cached = app.matches[confirmed.confirmation]
    app.matches[confirmed.confirmation] = (0, *cached[1:])
    with pytest.raises(RuntimeError, match="confirm"):
        app.start(confirmed)
    assert not app.jobs


def test_geocode_candidates_and_selected_match_reach_pipeline(tmp_path):
    second = {**MATCH, "matchedAddress": "414 GRANT AVE, PITTSBURGH, PA, 15219",
              "coordinates": {"y": 40.45, "x": -80.01}}
    calls = []
    async def resolver(req):
        return [MATCH, second], "https://geocoding.geo.census.gov/result"
    async def executor(req, ctx):
        calls.append((req, ctx))
        return outcome_fixture()
    app = App(tmp_path, executor, resolver)
    headers, body = request(app, "/api/geocode", method="POST", payload={"address": "414 Grant Street"})
    assert b"200 OK" in headers
    candidates = json.loads(body)["candidates"]
    assert len(candidates) == 2 and not app.jobs and not calls
    job = app.start(ResearchRequest(address="414 Grant Street", channels=["web"],
                    topics=["restaurant_reviews"], confirmation=candidates[1]["confirmation"]))
    assert wait_for_job(app, job["id"])["status"] == "complete"
    req, ctx = calls[0]
    assert req.address == second["matchedAddress"]
    assert req.geography == "PITTSBURGH, PA"
    assert ctx.confirmed_geocode[0] == second


async def test_confirmed_geocode_is_reused_without_network():
    from surreal_estate.channels.apis.census import CensusGeocoder
    ctx = RunContext(confirmed_geocode=(MATCH, "https://geocoding.geo.census.gov/result"))
    geocoder = CensusGeocoder(None)
    result = await geocoder.fetch(fixture_case(), ctx)
    assert geocoder.location.latitude == MATCH["coordinates"]["y"]
    assert result.evidence[0].details["matched_address"] == MATCH["matchedAddress"]
    assert "user_confirmed_match" in result.observations[0].flags
    assert not ctx.counts


@pytest.mark.parametrize("mode", ["empty", "error", "invalid"])
def test_geocode_failures_never_start_research(tmp_path, mode):
    async def resolver(req):
        if mode == "error":
            raise RuntimeError("SECRET_TOKEN")
        if mode == "invalid":
            return [{**MATCH, "coordinates": {"x": 999, "y": 0}}], "https://example.org"
        return [], "https://example.org"
    app = App(tmp_path, fixture_executor, resolver)
    headers, body = request(app, "/api/geocode", method="POST", payload={"address": "414 Grant Street"})
    assert (b"200 OK" if mode == "empty" else b"502 Bad Gateway") in headers
    assert b"SECRET_TOKEN" not in body and not app.jobs and not app.matches
    if mode == "empty":
        assert json.loads(body) == {"candidates": []}


@pytest.mark.parametrize("kwargs", [{"token": False}, {"host": "evil.test"}, {"origin": "https://evil.test"}])
def test_geocode_requires_same_origin_and_csrf(tmp_path, kwargs):
    app = App(tmp_path, fixture_executor, fixture_resolver)
    headers, _ = request(app, "/api/geocode", method="POST", payload={"address": "414 Grant Street"}, **kwargs)
    assert b"403 Forbidden" in headers and not app.matches


def test_progress_follows_trace_and_selected_channels():
    job = dict(status='running', channels=['apis', 'web'])
    ctx = RunContext()
    ctx.trace.extend(['channel:apis:started', 'source:census:geocoding:started'])
    progress = App.progress(job, ctx)
    assert progress['steps'][0]['state'] == 'active'
    assert progress['sources_checked'] == 0
    assert progress['detail'] == 'Checking the address'
    ctx.trace.extend(['source:census:geocoding:finished', 'channel:apis:finished',
                      'planner:started', 'planner:validated', 'channel:web:started'])
    progress = App.progress(job, ctx)
    assert [s['state'] for s in progress['steps']] == ['done', 'done', 'active', 'waiting']
    assert progress['sources_checked'] == 1
    assert 'percentage' not in progress
    web_only = App.progress(dict(status='running', channels=['web']), RunContext())
    assert all(s['id'] != 'apis' for s in web_only['steps'])


def test_progress_does_not_claim_unstarted_channels_finished():
    ctx = RunContext()
    ctx.trace.extend(['planner:started'])
    job = dict(status='running', channels=['web'], stage='report')
    progress = App.progress(job, ctx)
    assert [s['state'] for s in progress['steps']] == ['done', 'skipped', 'active']
    job.update(status='complete', progress=progress)
    assert [s['state'] for s in App.progress(job)['steps']] == ['done', 'skipped', 'done']


def test_closure_descriptions_are_visible_in_saved_records_without_dates():
    from surreal_estate.models import Evidence
    from surreal_estate.synthesis.report_visuals import closure_details
    item = Evidence(provider='wprdc_closures', uri='https://example.org/permit',
                    title='Permit', excerpt='Old statement has no work description', retention='persistent',
                    kind='official_record', details={'record': {'closure_id':'C1', 'primary_street':'GRANT ST',
                    'from_street':'A STREET', 'to_street':'B STREET',
                    'work_description':'DLCO DOING HPFF MANHOLE INSPECTIONS MH 3514 <script>',
                    'to_date':None}})
    html = closure_details([item])
    assert 'DLCO DOING HPFF MANHOLE INSPECTIONS MH 3514 &lt;script&gt;' in html
    assert '<script>' not in html
    assert 'A STREET to B STREET' in html
    assert 'End date unknown' in html
    assert 'https://example.org/permit' in html
    assert 'do not confirm' in html
