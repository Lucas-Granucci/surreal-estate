import json

import httpx
import pytest

from surreal_estate.channels.apis.channel import DataPlanner, StructuredDataChannel
from surreal_estate.channels.apis.common import Location, public_json
from surreal_estate.channels.apis.wprdc import Assessments, Closures, Permits
from surreal_estate.evals.fixtures import fixture_case
from surreal_estate.models import ResearchPlan, RunReport
from surreal_estate.orchestrator.context import Budget, RunContext
from surreal_estate.orchestrator.runner import run
from surreal_estate.store.export import build_export
from surreal_estate.synthesis.dashboard import render_dashboard
from surreal_estate.synthesis.frontend import build_frontend_response

DATASETS = {
    "property-assessments": (
        "Property Assessments Parcel Data (API version)",
        "11111111-1111-4111-8111-111111111111",
    ),
    "pli-permits": ("PLI Permits", "22222222-2222-4222-8222-222222222222"),
    "street-closures": ("Street Closures", "33333333-3333-4333-8333-333333333333"),
}


def matched_location(pittsburgh=True):
    return Location(
        40.438,
        -79.996,
        "414 GRANT ST, PITTSBURGH, PA, 15219",
        {"streetName": "GRANT", "suffixType": "ST", "zip": "15219", "state": "PA"},
        {
            "Counties": [{"GEOID": "42003"}],
            "Incorporated Places": [{"GEOID": "4261000" if pittsburgh else "4200000"}],
        },
    )


class PublicAPIs:
    def __init__(self):
        self.requests = []
        self.location = matched_location()
        self.ambiguous = False
        self.fail_provider = None
        self.overpass_remark = False
        self.assessments = [
            {
                "PARID": "0002J00002000000",
                "PROPERTYHOUSENUM": "414",
                "PROPERTYADDRESS": "GRANT ST",
                "PROPERTYZIP": "15219",
                "PROPERTYSTATE": "PA",
                "YEARBLT": None,
                "COUNTYTOTAL": 123400,
                "ASOFDATE": "2026-09-30",
            }
        ]
        self.permits = [
            {
                "permit_id": "BDA-2026-1",
                "permit_type": "Building & Development Application",
                "parcel_num": "0002J00002000000",
                "issue_date": "2026-01-05",
                "work_description": "Alterations",
                "status": "ISSUED",
            }
        ]
        self.closures = [
            {
                "closure_id": "C1",
                "permit_id": "P1",
                "roadway_id": "R1",
                "primary_street": "GRANT ST",
                "from_date": "2026-01-01",
                "to_date": None,
                "active": None,
                "segment_num": 1,
                "geometry": "[[40.437, -79.996], [40.439, -79.996]]",
            }
        ]
        self.total_override = None

    def __call__(self, request):
        self.requests.append(request)
        path, params = request.url.path, request.url.params
        if self.fail_provider and self.fail_provider in str(request.url):
            return httpx.Response(503, text="upstream unavailable")
        if "geocoder" in path:
            loc = self.location
            match = {
                "matchedAddress": loc.address,
                "coordinates": {"x": loc.longitude, "y": loc.latitude},
                "addressComponents": loc.components,
                "geographies": loc.geographies,
            }
            return httpx.Response(
                200,
                json={"result": {"addressMatches": [match, match] if self.ambiguous else [match]}},
            )
        if path.endswith("package_show"):
            dataset = params["id"]
            name, resource_id = DATASETS[dataset]
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "license_id": "cc-zero" if dataset == "property-assessments" else "cc-by",
                        "metadata_modified": "2026-10-10",
                        "resources": [
                            {
                                "id": resource_id,
                                "name": name,
                                "datastore_active": True,
                                "last_modified": "2026-10-09",
                            },
                            {
                                "id": "old-resource",
                                "name": name + " (deprecated)",
                                "datastore_active": True,
                            },
                        ],
                    },
                },
            )
        if path.endswith("datastore_search"):
            dataset = next(k for k, v in DATASETS.items() if v[1] == params["resource_id"])
            assert "owner" not in params["fields"].lower()
            records = {
                "property-assessments": self.assessments,
                "pli-permits": self.permits,
                "street-closures": self.closures,
            }[dataset]
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "fields": [{"id": k} for k in params["fields"].split(",")],
                        "records": records,
                        "total": self.total_override or len(records),
                    },
                },
            )
        if "/MapServer/" in path:
            assert params["geometry"] == "-79.996,40.438" and params["inSR"] == "4326"
            attrs = (
                {
                    "OBJECTID": 1,
                    "DFIRM_ID": "42003C",
                    "FLD_AR_ID": "A1",
                    "FLD_ZONE": "X",
                    "SFHA_TF": "F",
                }
                if "/28/" in path
                else {"OBJECTID": 2, "FIRM_PAN": "42003C0001", "EFF_DATE": 1415836800000}
            )
            return httpx.Response(200, json={"features": [{"attributes": attrs}]})
        if path.endswith("interpreter"):
            assert request.method == "POST"
            assert request.url.host == "overpass-api.de"
            assert request.headers["content-type"] == "text/plain; charset=utf-8"
            assert "github.com/Lucas-Granucci/surreal-estate" in request.headers["user-agent"]
            query = request.content.decode()
            assert query.startswith("[out:json]") and "out body center 51;" in query
            assert "data=" not in query and "%5B" not in query
            assert "around:1000,40.438,-79.996" in query and "51" in query
            return httpx.Response(
                200,
                json={
                    "elements": [
                        {
                            "type": "node",
                            "id": 10,
                            "lat": 40.438,
                            "lon": -79.995,
                            "tags": {"amenity": "pharmacy", "name": "Example Pharmacy"},
                        }
                    ],
                    "osm3s": {"timestamp_osm_base": "2026-10-10T00:00:00Z"},
                    **({"remark": "runtime timeout"} if self.overpass_remark else {}),
                },
            )
        raise AssertionError(str(request.url))


async def fetch(apis, budget=None):
    ctx = RunContext(budget=budget or Budget())
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        result = await StructuredDataChannel(http).run(fixture_case(), ctx)
    return result, ctx


async def test_default_sources_return_provenance_and_survive_export():
    apis = PublicAPIs()
    result, ctx = await fetch(apis)
    assert len(result.coverage) == 7
    assert all(c.status == "complete" for c in result.coverage)
    assert ctx.counts["api"] == 10 == sum(c.queries_run for c in result.coverage)
    assert len(result.evidence) == 10
    assessment = next(e for e in result.evidence if e.provider == "wprdc_assessments")
    assert "year built" not in assessment.excerpt
    assert assessment.details["record"]["YEARBLT"] is None
    assert assessment.record_id == "0002J00002000000"
    assert assessment.source_updated_at == "2026-10-09"
    assert assessment.record_date == "2026-09-30"
    assert "unique_exact" in assessment.match_method
    osm = next(e for e in result.evidence if e.record_id == "amenities:pharmacies")
    assert osm.kind == "reported" and "OpenStreetMap contributors" in osm.attribution
    assert osm.details["nearest_returned_center_distance_m"] > 0
    assert osm.details["members"][0]["tags"]["amenity"] == "pharmacy"
    exported = build_export(RunReport(case=fixture_case(), result=result), ctx.policy)
    assert exported.report.result.evidence == result.evidence


async def test_ambiguous_geocode_blocks_dependent_requests():
    apis = PublicAPIs()
    apis.ambiguous = True
    result, ctx = await fetch(apis)
    assert not result.evidence
    assert len(result.coverage) == 7
    assert all(c.status == "blocked" for c in result.coverage)
    assert ctx.counts["api"] == len(apis.requests) == 1


async def test_shared_address_parcels_are_not_arbitrarily_selected():
    apis = PublicAPIs()
    apis.assessments.append({**apis.assessments[0], "PARID": "DIFFERENT"})
    result, _ = await fetch(apis)
    assert next(c for c in result.coverage if c.topic == "property_assessment").status == "blocked"
    assert next(c for c in result.coverage if c.topic == "building_permits").status == "blocked"
    assert not any(e.provider in {"wprdc_assessments", "wprdc_permits"} for e in result.evidence)
    assert any(e.provider == "fema_nfhl" for e in result.evidence)


async def test_postal_city_does_not_enable_city_sources_outside_jurisdiction():
    apis = PublicAPIs()
    apis.location = matched_location(pittsburgh=False)
    result, _ = await fetch(apis)
    assert all(
        c.status == "blocked"
        for c in result.coverage
        if c.provider in {"wprdc_permits", "wprdc_closures"}
    )
    assert not any(
        r.url.params.get("id") in {"pli-permits", "street-closures"} for r in apis.requests
    )
    assert any(e.provider == "wprdc_assessments" for e in result.evidence)


async def test_failure_does_not_erase_completed_sources_or_skip_later_sources():
    apis = PublicAPIs()
    apis.fail_provider = "hazards.fema.gov"
    result, _ = await fetch(apis)
    assert all(c.status == "error" for c in result.coverage if c.provider == "fema_nfhl")
    assert any(e.provider == "wprdc_assessments" for e in result.evidence)
    assert any(e.provider == "openstreetmap" for e in result.evidence)
    assert any(e.provider == "wprdc_closures" for e in result.evidence)


async def test_budget_exhaustion_retains_data_and_marks_every_remaining_provider():
    apis = PublicAPIs()
    result, ctx = await fetch(apis, Budget(max_api_calls=3))
    assert ctx.counts["api"] == len(apis.requests) == 3
    assert len(result.evidence) == 2
    assert len(result.coverage) == 7
    assert all(c.status == "truncated" for c in result.coverage[2:])


async def test_partial_overpass_response_is_not_treated_as_complete():
    apis = PublicAPIs()
    apis.overpass_remark = True
    result, _ = await fetch(apis)
    assert next(c for c in result.coverage if c.provider == "openstreetmap").status == "error"
    assert not any(e.provider == "openstreetmap" for e in result.evidence)


@pytest.mark.parametrize(
    "address",
    [
        "414 Grant St Apt 2, Pittsburgh PA 15219",
        "414 1/2 Grant St, Pittsburgh PA 15219",
        "414-416 Grant St, Pittsburgh PA 15219",
    ],
)
async def test_complex_addresses_require_explicit_parcel_selection(address):
    apis = PublicAPIs()
    case = fixture_case().model_copy(update={"address": address})
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        result = await Assessments(http).fetch(case, RunContext(), matched_location())
    assert result.coverage[0].status == "blocked" and not apis.requests


async def test_closures_filter_distance_dates_and_record_invalid_rows():
    apis = PublicAPIs()
    base = apis.closures[0]
    apis.closures += [
        {**base, "closure_id": "expired", "to_date": "2020-01-01"},
        {**base, "closure_id": "future", "from_date": "2099-01-01"},
        {**base, "closure_id": "far", "geometry": "[[41, -79], [41.1, -79]]"},
        {**base, "closure_id": "invalid", "geometry": "invalid"},
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        result = await Closures(http).fetch(fixture_case(), RunContext(), matched_location())
    assert len(result.evidence) == 1 and result.evidence[0].record_id == "C1:R1"
    assert result.coverage[0].status == "truncated"
    assert "1 records lacked" in result.coverage[0].reason
    assert result.evidence[0].details["approximate_segment_distance_m"] == 0


async def test_default_data_runs_without_llm_and_despite_web_planning_failure():
    class BrokenPlanner:
        async def plan(self, *args):
            raise ValueError("bad model response")

    for planner in [DataPlanner(), BrokenPlanner()]:
        apis = PublicAPIs()
        async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
            outcome = await run(fixture_case(), RunContext(), planner, StructuredDataChannel(http))
        assert len(outcome.report.result.evidence) == 10
        html = render_dashboard(build_frontend_response(outcome))
        assert "OpenStreetMap contributors" in html and "2026-10-09" in html
        assert "structured records" in html and "Structured fields and provenance" in html
        assert not any("11434" in str(r.url) for r in apis.requests)


async def test_model_cannot_omit_baseline_sources_or_cause_duplicate_calls():
    class WebOnlyPlanner:
        async def plan(self, *args):
            return ResearchPlan(channels=["listing"])

    apis = PublicAPIs()
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        outcome = await run(
            fixture_case(), RunContext(), WebOnlyPlanner(), StructuredDataChannel(http)
        )
    assert outcome.report.plan.channels == ["apis", "listing"]
    assert len(apis.requests) == 10


async def test_provider_endpoint_policy_blocks_dispatch():
    apis = PublicAPIs()
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        with pytest.raises(ValueError, match="outside source policy"):
            await public_json(http, RunContext(), "wprdc_permits", "https://example.org/data")
    assert not apis.requests


@pytest.mark.parametrize("change", ["schema", "license", "resource"])
async def test_catalog_or_schema_changes_fail_closed(change):
    apis = PublicAPIs()

    def changed(request):
        response = apis(request)
        payload = response.json()
        if (
            request.url.path.endswith("package_show")
            and request.url.params["id"] == "property-assessments"
        ):
            if change == "license":
                payload["result"]["license_id"] = "unknown"
            elif change == "resource":
                payload["result"]["resources"][0]["datastore_active"] = False
        elif request.url.path.endswith("datastore_search") and change == "schema":
            payload["result"]["fields"] = []
        return httpx.Response(200, json=payload)

    result, _ = await fetch(changed)
    assert next(c for c in result.coverage if c.provider == "wprdc_assessments").status == "error"
    assert next(c for c in result.coverage if c.provider == "wprdc_permits").status == "blocked"
    assert not any(e.provider == "wprdc_assessments" for e in result.evidence)


async def test_wrong_address_records_and_unrequested_personal_columns_are_not_retained():
    apis = PublicAPIs()
    apis.assessments[0]["owner_name"] = "UNREQUESTED PERSONAL FIELD"
    apis.assessments.append({**apis.assessments[0], "PROPERTYZIP": "15000", "PARID": "WRONG"})
    apis.permits.append({**apis.permits[0], "parcel_num": "WRONG", "permit_id": "WRONG"})
    result, _ = await fetch(apis)
    assert "UNREQUESTED PERSONAL FIELD" not in result.model_dump_json()
    assert "WRONG" not in result.model_dump_json()
    assert sum(e.provider == "wprdc_assessments" for e in result.evidence) == 1
    assert sum(e.provider == "wprdc_permits" for e in result.evidence) == 1


async def test_result_caps_are_reported_instead_of_claiming_completeness():
    apis = PublicAPIs()
    apis.total_override = 500
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        permits = await Permits(http).fetch(
            fixture_case(), RunContext(), matched_location(), "0002J00002000000"
        )
        closures = await Closures(http).fetch(fixture_case(), RunContext(), matched_location())
    assert permits.coverage[0].status == closures.coverage[0].status == "truncated"


async def test_fema_http_200_error_and_empty_features_are_distinct():
    from surreal_estate.channels.apis.spatial import FEMA

    for payload, raises in [({"error": {"code": 500}}, True), ({"features": []}, False)]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
        ) as http:
            if raises:
                with pytest.raises(ValueError, match="FEMA"):
                    await FEMA(http).fetch(fixture_case(), RunContext(), matched_location())
            else:
                result = await FEMA(http).fetch(fixture_case(), RunContext(), matched_location())
                assert result.coverage[0].status == "empty" and not result.observations
                assert "not a finding of no flood risk" in result.coverage[0].reason


async def test_oversized_public_response_is_rejected():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b" " * 2_000_001))
    ) as http:
        with pytest.raises(ValueError, match="size limit"):
            await public_json(http, RunContext(), "census", "https://geocoding.geo.census.gov/test")


async def test_no_automatic_retries_on_public_api_rate_limit():
    requests = []

    def limited(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    result, _ = await fetch(limited)
    assert len(requests) == 1
    assert result.coverage[0].status == "error"
    assert all(c.status == "blocked" for c in result.coverage[1:])


async def test_global_timeout_keeps_completed_baseline_records():
    import asyncio

    apis = PublicAPIs()
    partial, _ = await fetch(apis)

    class InterruptedChannel:
        default_enabled = True
        partial_result = partial

        async def run(self, *args):
            await asyncio.sleep(1)

    outcome = await run(
        fixture_case(),
        RunContext(budget=Budget(deadline_seconds=0.01)),
        DataPlanner(),
        InterruptedChannel(),
    )
    assert outcome.report.result.evidence == partial.evidence
    assert any(
        c.topic == "research" and c.status == "truncated" for c in outcome.report.result.coverage
    )


async def test_cli_selects_default_channel_without_instantiating_models(monkeypatch):
    from argparse import Namespace
    from surreal_estate import cli
    from surreal_estate.orchestrator.runner import RunOutcome
    from surreal_estate.models import ChannelResult

    seen = []

    async def fake_run(case, ctx, planner, api_channel, **kwargs):
        seen.append((planner, api_channel, kwargs))
        return RunOutcome(RunReport(case=case, result=ChannelResult()), [])

    def forbidden(*args, **kwargs):
        raise AssertionError("Structured-only runs must not initialize models")

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli, "NemotronClient", forbidden)
    monkeypatch.setattr(cli, "GroundedSearchClient", forbidden)
    await cli.execute(
        Namespace(
            command="research",
            address=fixture_case().address,
            geography=fixture_case().geography,
            web=False,
            db=None,
            save_json=False,
        )
    )
    assert isinstance(seen[0][0], DataPlanner)
    assert isinstance(seen[0][1], StructuredDataChannel)


async def test_overpass_raw_post_has_queue_time_and_preserves_way_centers():
    from surreal_estate.channels.apis.spatial import OVERPASS_ENDPOINT, OpenStreetMap

    requests = []

    def overpass(request):
        requests.append(request)
        assert str(request.url) == OVERPASS_ENDPOINT
        assert request.method == "POST"
        assert request.content.startswith(b"[out:json][timeout:10]")
        assert request.headers["content-type"] == "text/plain; charset=utf-8"
        assert "github.com/Lucas-Granucci/surreal-estate" in request.headers["user-agent"]
        assert request.extensions["timeout"]["read"] == 35
        return httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "way",
                        "id": 22,
                        "center": {"lat": 40.438, "lon": -79.995},
                        "tags": {"amenity": "school", "name": "Example School"},
                    }
                ]
            },
        )

    ctx = RunContext()
    async with httpx.AsyncClient(transport=httpx.MockTransport(overpass)) as http:
        result = await OpenStreetMap(http).fetch(fixture_case(), ctx, matched_location())
    assert len(requests) == ctx.counts["api"] == 1
    assert result.coverage[0].status == "complete"
    assert result.evidence[0].details["query_endpoint"] == OVERPASS_ENDPOINT
    assert result.evidence[0].details["nearest_returned_center_distance_m"] > 0
    assert "point/center" in result.observations[0].statement


async def test_overpass_honors_smaller_run_request_limit():
    from surreal_estate.channels.apis.spatial import OpenStreetMap

    def overpass(request):
        assert request.extensions["timeout"]["read"] == 3
        return httpx.Response(200, json={"elements": []})

    ctx = RunContext(budget=Budget(request_seconds=3))
    async with httpx.AsyncClient(transport=httpx.MockTransport(overpass)) as http:
        result = await OpenStreetMap(http).fetch(fixture_case(), ctx, matched_location())
    assert result.coverage[0].status == "empty"


async def test_overpass_record_cap_preserves_useful_results():
    from surreal_estate.channels.apis.spatial import OpenStreetMap

    elements = [
        {"type": "node", "id": i, "lat": 40.438, "lon": -79.996, "tags": {"highway": "bus_stop"}}
        for i in range(1, 102)
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"elements": elements}))
    ) as http:
        result = await OpenStreetMap(http).fetch(fixture_case(), RunContext(), matched_location())
    assert result.coverage[0].status == "complete"
    assert len(result.evidence) == len(result.observations) == 4
    transit = next(e for e in result.evidence if e.details["category"] == "transit")
    assert len(transit.details["members"]) == 50
    assert transit.details["count_is_lower_bound"]
    assert "at least 50" in transit.excerpt


async def test_public_json_rejects_conflicting_request_bodies_before_dispatch():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: pytest.fail("unexpected request"))
    ) as http:
        with pytest.raises(ValueError, match="not both"):
            await public_json(
                http,
                RunContext(),
                "openstreetmap",
                "https://overpass-api.de/api/interpreter",
                data={"data": "query"},
                content="query",
            )


async def test_amenity_summary_categories_and_independent_caps():
    from surreal_estate.channels.apis.spatial import OpenStreetMap

    school = {
        "type": "way",
        "id": 999,
        "center": {"lat": 40.438, "lon": -79.995},
        "tags": {"amenity": "school", "name": "A School"},
    }
    transit = [
        {
            "type": "node",
            "id": i,
            "lat": 40.438,
            "lon": -79.996,
            "tags": {"highway": "bus_stop", "public_transport": "platform"},
        }
        for i in range(1, 52)
    ]

    def response(request):
        query = request.content.decode()
        for category in ("schools", "groceries", "transit", "pharmacies"):
            assert f")->.{category};.{category} out body center 51;" in query
        assert all(word not in query for word in ("restaurant", "cafe", "park", "clinic"))
        return httpx.Response(200, json={"elements": transit + [school, transit[0]]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        result = await OpenStreetMap(http).fetch(fixture_case(), RunContext(), matched_location())
    assert len(result.observations) == len(result.evidence) == 4
    by_category = {e.details["category"]: e for e in result.evidence}
    assert by_category["schools"].details["mapped_feature_count"] == 1
    assert not by_category["schools"].details["count_is_lower_bound"]
    assert by_category["transit"].details["mapped_feature_count"] == 50
    assert by_category["transit"].details["count_is_lower_bound"]
    assert by_category["groceries"].details["mapped_feature_count"] == 0
    assert "does not establish that none exist" in by_category["groceries"].excerpt
    assert "A School" not in " ".join(o.statement for o in result.observations)


async def test_duplicate_stop_tags_count_once_and_excluded_places_are_ignored():
    from surreal_estate.channels.apis.spatial import OpenStreetMap

    def node(identifier, tags):
        return {"type": "node", "id": identifier, "lat": 40.438, "lon": -79.996, "tags": tags}

    stop = node(1, {"highway": "bus_stop", "public_transport": "platform"})
    elements = [
        stop,
        stop,
        node(2, {"amenity": "restaurant", "name": "Excluded Restaurant"}),
        node(3, {"amenity": "clinic"}),
        node(4, {"shop": "supermarket", "name": "Example Grocery"}),
        node(5, {"amenity": "pharmacy", "name": "Example Pharmacy"}),
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"elements": elements}))
    ) as http:
        result = await OpenStreetMap(http).fetch(fixture_case(), RunContext(), matched_location())
    assert (
        next(e for e in result.evidence if e.details["category"] == "transit").details[
            "mapped_feature_count"
        ]
        == 1
    )
    assert "Excluded Restaurant" not in result.model_dump_json()
    assert all("Example" not in o.statement for o in result.observations)
    assert "Example Pharmacy" in result.model_dump_json()


async def test_supporting_place_names_stay_inside_closed_dashboard_details():
    from html.parser import HTMLParser
    from surreal_estate.orchestrator.runner import RunOutcome
    from surreal_estate.synthesis.dossier import synthesize

    class VisibleText(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.hidden_details = []
            self.text = []
            self.supporting_sections = 0

        def handle_starttag(self, tag, attrs):
            if tag == "details":
                attrs = dict(attrs)
                hidden = "open" not in attrs
                self.hidden_details.append(hidden)
                self.depth += int(hidden)
                if attrs.get("class") == "amenity-members":
                    self.supporting_sections += 1
                    assert "open" not in attrs

        def handle_endtag(self, tag):
            if tag == "details":
                self.depth -= int(self.hidden_details.pop())

        def handle_data(self, data):
            if not self.depth:
                self.text.append(data)

    result, _ = await fetch(PublicAPIs())
    report = RunReport(case=fixture_case(), result=result, claims=synthesize(result))
    html = render_dashboard(build_frontend_response(RunOutcome(report, [])))
    visible = VisibleText()
    visible.feed(html)
    assert visible.supporting_sections == 1
    assert "Example Pharmacy" not in " ".join(visible.text)
    assert "Example Pharmacy" in html
    assert "Schools:" in " ".join(visible.text)
    assert "Pharmacies:" in " ".join(visible.text)


@pytest.mark.parametrize("address,geography,expected", [
    ("414 Grant Street", "Pittsburgh, Pennsylvania", "414 Grant Street, Pittsburgh, Pennsylvania"),
    (" 414 Grant Street ", "Pittsburgh, Pennsylvania", "414 Grant Street, Pittsburgh, Pennsylvania"),
    ("414 Grant Street, Apt 2", "Pittsburgh, Pennsylvania", "414 Grant Street, Apt 2, Pittsburgh, Pennsylvania"),
    ("414 Grant Street, Pittsburgh", "Pittsburgh, Pennsylvania", "414 Grant Street, Pittsburgh, Pennsylvania"),
    ("414 Grant Street Pittsburgh", "Pittsburgh, Pennsylvania", "414 Grant Street Pittsburgh, Pennsylvania"),
    ("414 Grant Street, Pittsburgh, PA 15219", "Pittsburgh, Pennsylvania", "414 Grant Street, Pittsburgh, PA 15219"),
    ("414 Grant Street Pittsburgh PA", "Pittsburgh, Pennsylvania", "414 Grant Street Pittsburgh PA"),
    ("414 Grant Street, Pittsburgh, Pennsylvania", "Pittsburgh, Pennsylvania", "414 Grant Street, Pittsburgh, Pennsylvania"),
    ("123 Main Street, Albany, NY", "Pittsburgh, Pennsylvania", "123 Main Street, Albany, NY"),
    ("123 Main Street, Albany", "Pittsburgh, Pennsylvania", "123 Main Street, Albany"),
    ("123 Main Street 12207-1234", "Pittsburgh, Pennsylvania", "123 Main Street 12207-1234"),
])
def test_geocoding_completes_street_input_without_overwriting_locality(address, geography, expected):
    from surreal_estate.channels.apis.census import geocoding_address
    from surreal_estate.models import PropertyCase
    assert geocoding_address(PropertyCase(address=address, geography=geography)) == expected


async def test_street_only_address_unlocks_dependent_providers():
    from surreal_estate.models import PropertyCase

    class RequiresLocality(PublicAPIs):
        def __call__(self, request):
            if "geocoder" in request.url.path and request.url.params["address"] != "414 Grant Street, Pittsburgh, Pennsylvania":
                return httpx.Response(200, json={"result": {"addressMatches": []}})
            return super().__call__(request)

    apis = RequiresLocality()
    case = PropertyCase(address="414 Grant Street", geography="Pittsburgh, Pennsylvania")
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        result = await StructuredDataChannel(http).run(case, RunContext())
    assert all(c.status == "complete" for c in result.coverage)
    assert len(apis.requests) == 10
    census = next(e for e in result.evidence if e.provider == "census")
    assert census.details["submitted_address"] == "414 Grant Street, Pittsburgh, Pennsylvania"
    assert case.address == "414 Grant Street"


async def test_no_match_gives_an_actionable_address_error():
    from surreal_estate.channels.apis.census import CensusGeocoder
    from surreal_estate.models import PropertyCase
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"result": {"addressMatches": []}}))) as http:
        result = await CensusGeocoder(http).fetch(PropertyCase(address="414 Grant Street", geography="Pittsburgh, Pennsylvania"), RunContext())
    assert result.coverage[0].status == "empty"
    assert "414 Grant Street, Pittsburgh, Pennsylvania" in result.coverage[0].reason
    assert "ZIP code" in result.coverage[0].reason


async def test_ambiguous_parcels_return_candidates_without_attaching_evidence():
    apis = PublicAPIs()
    apis.assessments.append({**apis.assessments[0], "PARID": "SECOND", "USEDESC": "COUNTY GOVERNMENT"})
    result, _ = await fetch(apis)
    assessment = next(c for c in result.coverage if c.topic == "property_assessment")
    assert assessment.status == "blocked"
    assert {candidate.parcel_id for candidate in assessment.parcel_candidates} == {"0002J00002000000", "SECOND"}
    assert not any(e.provider == "wprdc_assessments" for e in result.evidence)
    assert not any(r.url.params.get("id") == "pli-permits" for r in apis.requests)
    assert all("OWNER" not in c.model_dump_json() for c in assessment.parcel_candidates)


@pytest.mark.parametrize("parcel_id,expected", [("0002J00002000000", "complete"), ("UNRELATED", "blocked")])
async def test_explicit_parcel_choice_is_validated_before_permits(parcel_id, expected):
    apis = PublicAPIs()
    apis.assessments.append({**apis.assessments[0], "PARID": "SECOND"})
    case = fixture_case().model_copy(update={"parcel_id": parcel_id})
    async with httpx.AsyncClient(transport=httpx.MockTransport(apis)) as http:
        result = await StructuredDataChannel(http).run(case, RunContext())
    assert next(c for c in result.coverage if c.topic == "property_assessment").status == expected
    permit_requests = [r for r in apis.requests if r.url.params.get("id") == "pli-permits"]
    if expected == "complete":
        assert permit_requests
        assert next(c for c in result.coverage if c.topic == "building_permits").status == "complete"
        evidence = next(e for e in result.evidence if e.provider == "wprdc_assessments")
        assert evidence.record_id == parcel_id and evidence.match_method == "user_selected_exact_address_candidate"
    else:
        assert not permit_requests
        assert not any(e.provider == "wprdc_assessments" for e in result.evidence)


async def test_fema_connection_diagnostic_names_fema_not_ollama_or_exception_text():
    apis = PublicAPIs()
    def transport(request):
        if request.url.host == "hazards.fema.gov":
            raise httpx.ConnectError("SECRET provider response", request=request)
        return apis(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        result = await StructuredDataChannel(http).run(fixture_case(), RunContext())
    for item in result.coverage:
        if item.provider == "fema_nfhl":
            assert item.status == "error" and "FEMA (hazards.fema.gov)" in item.reason
            assert "before an HTTP response" in item.reason
            assert "Ollama" not in item.reason and "SECRET" not in item.reason
    assert next(c for c in result.coverage if c.topic == "mapped_amenities").status == "complete"
