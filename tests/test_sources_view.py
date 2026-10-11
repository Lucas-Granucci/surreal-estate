import httpx
from test_frontend import outcome_fixture

from surreal_estate.channels.apis.census import CensusGeocoder
from surreal_estate.models import Coverage, Evidence, GroundingChunk
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.synthesis.sources_view import render_sources
from surreal_estate.synthesis.viewer import render_html


def test_sources_at_top_show_actual_apis_uploads_and_unique_web_links():
    outcome = outcome_fixture()
    outcome.report.result.evidence.extend(
        [
            Evidence(
                provider="census",
                uri="https://geocoding.geo.census.gov/geocoder/test",
                title="Census match",
                excerpt="Match",
                retention="persistent",
                kind="official_record",
            ),
            Evidence(
                provider="user_upload",
                uri="https://example.org/document/hoa",
                title="HOA budget.pdf",
                excerpt="Budget",
                retention="persistent",
                kind="user_document",
            ),
        ]
    )
    outcome.report.result.coverage.append(
        Coverage(
            channel="apis",
            provider="census",
            topic="geocoding",
            status="complete",
            reason="Matched",
        )
    )
    html = render_html(outcome)
    inventory = render_sources(outcome)
    assert html.index("Sources for this run") < html.index("Research plan")
    assert "U.S. Census Geocoder" in inventory and "Census match" in inventory
    assert "HOA budget.pdf" in inventory
    assert "Gemini API + Google Search grounding" in inventory
    assert "1 source links · 1 cited" in inventory
    assert inventory.count('href="https://example.org/review"') == 1
    assert "Search result" in inventory and "Claim re-check" in inventory
    assert "FEMA" not in inventory and "Yelp" not in inventory


def test_source_inventory_honest_attempts_and_missing_uploads():
    outcome = outcome_fixture()
    outcome.displays.clear()
    outcome.report.result.coverage.append(
        Coverage(
            channel="apis", provider="census", topic="geocoding", status="error", reason="Failure"
        )
    )
    html = render_sources(outcome)
    assert "U.S. Census Geocoder" in html and "error" in html
    assert "Attempt recorded; no evidence returned" in html
    assert "No uploaded documents, photos or floorplans recorded" in html
    assert "Upload and extraction flow is not yet implemented" in html
    assert "No web source links available" in html
    assert "Gemini API" not in html


def test_source_titles_escaped_and_returned_links_not_promoted_to_citations():
    outcome = outcome_fixture()
    outcome.displays[1].response = outcome.displays[1].response.model_copy(
        update={
            "chunks": [
                GroundingChunk(uri="https://example.org/uncited", title="<script>bad()</script>")
            ],
            "supports": [],
        }
    )
    html = render_sources(outcome)
    assert "2 source links · 1 cited" in html
    assert "returned without a support mapping" in html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in html
    assert "<script>" not in html


async def test_census_empty_records_attempted_provider():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"result": {"addressMatches": []}})
        )
    ) as http:
        result = await CensusGeocoder(http).fetch(outcome_fixture().report.case, RunContext())
    assert result.coverage[0].provider == "census"
    assert result.coverage[0].status == "empty"
    assert not result.evidence
