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


def test_app_report_has_grouped_navigation_and_native_collapsible_sections():
    class Structure(HTMLParser):
        def __init__(self, html):
            super().__init__()
            self.sections = []
            self.disclosures = []
            self.groups = 0
            self.feed(html)

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "section":
                self.sections.append(attrs["id"])
            if tag == "details" and attrs.get("class") == "report-section":
                self.disclosures.append(attrs)
            if tag == "details" and attrs.get("class") == "nav-group":
                self.groups += 1

    html = render_dashboard(build_frontend_response(outcome_fixture()), app_mode=True)
    structure = Structure(html)
    assert len(structure.sections) == len(structure.disclosures)
    assert sum("open" in attrs for attrs in structure.disclosures) == 1
    assert structure.groups >= 2
    assert 'data-sections="expand"' in html and 'data-sections="collapse"' in html
    assert 'aria-label="At a glance"' not in html
    assert "PRIVATE-WEB" in html and "PRIVATE-CHECK" in html
    links = Links(html)
    assert len(links.ids) == len(set(links.ids))
    assert all(href[1:] in links.ids for href in links.hrefs if href.startswith("#"))


def test_empty_geocoding_result_is_in_gaps():
    outcome = outcome_fixture()
    item = outcome.report.result.coverage[0]
    item.topic = "geocoding"
    item.status = "empty"
    item.reason = "No address match; check city and state"
    html = render_dashboard(build_frontend_response(outcome), app_mode=True)
    gaps = html.split('<section id="gaps">', 1)[1].split('</section>', 1)[0]
    assert item.reason in gaps


def test_sidebar_and_report_have_identical_order_with_map_first():
    from surreal_estate.models import Coverage
    outcome = outcome_fixture()
    for topic in ["property_assessment", "flood_map_panels", "geocoding", "mapped_amenities", "street_closures"]:
        outcome.report.result.coverage.append(Coverage(channel="apis", topic=topic, status="complete", reason="Done"))
    html = render_dashboard(build_frontend_response(outcome), app_mode=True)
    rail = html.split('aria-label="Report sections"', 1)[1].split('</nav>', 1)[0]
    main = html.split('<main>', 1)[1]
    import re
    sidebar_targets = re.findall(r'href="#([^"]+)"', rail)
    main_sections = re.findall(r'<section id="([^"]+)"', main)
    assert sidebar_targets[1:] == main_sections
    assert main_sections[0] == "topic-0"
    first = main.split('<section id="topic-0">', 1)[1].split('</section>', 1)[0]
    assert "Around the block" in first and 'class="report-section" open' in first
    assert main.index('coverage-overview') < main.index('<section')
    assert main.index('<section id="findings">') > main.index('<section id="gaps">')


def test_visual_coverage_counts_exclude_unselected_channels_and_keep_error_links():
    from surreal_estate.models import Coverage
    from surreal_estate.synthesis.dashboard import coverage_summary
    rows = [Coverage(channel="apis", topic=topic, status=status, reason=reason) for topic, status, reason in [
        ("geocoding", "complete", "Matched"), ("flood_hazard", "error", "Cannot connect"),
        ("property_assessment", "blocked", "Choose a parcel"), ("street_closures", "empty", "No results"),
        ("research", "blocked", "Not selected for this run"),
    ]]
    html = coverage_summary(rows, {"flood_hazard": 1, "property_assessment": 2})
    assert '<strong>1/4</strong>' in html
    assert '1 completed, 1 blocked, 1 errors, 1 partial / no results' in html
    assert 'href="#topic-1"' in html and 'href="#topic-2"' in html
    assert html.count('width:25.00%') == 4


def test_parcel_candidate_links_preserve_address_and_selected_id():
    from surreal_estate.models import ParcelCandidate
    from surreal_estate.synthesis.dashboard import parcel_choices
    from urllib.parse import parse_qs, urlsplit
    case = outcome_fixture().report.case
    candidate = ParcelCandidate(parcel_id="0002E00284000000", address=case.address, property_use="<unsafe>", source_url="https://data.wprdc.org/dataset/property-assessments")
    html = parcel_choices([candidate], case, app_mode=True)
    assert "<unsafe>" not in html and "&lt;unsafe&gt;" in html
    href = next(h for h in Links(html).hrefs if h.startswith('/?'))
    params = parse_qs(urlsplit(href).query)
    assert params["address"] == [case.address]
    assert params["parcel_id"] == [candidate.parcel_id]
    assert params["geography"] == [case.geography]
