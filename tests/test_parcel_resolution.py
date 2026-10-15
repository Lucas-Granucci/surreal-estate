import json

import httpx
import pytest
from test_structured_sources import PublicAPIs, fetch

from surreal_estate.channels.apis.parcel_resolution import resolve_parcel
from surreal_estate.evals.fixtures import fixture_case
from surreal_estate.models import RunReport
from surreal_estate.orchestrator.context import Budget, RunContext
from surreal_estate.webapp.display import bench_response


def candidates():
    apis = PublicAPIs()
    apis.assessments.append({**apis.assessments[0], "PARID": "SECOND"})
    return apis


def address_point(parcel="SECOND", **overrides):
    return {
        "attributes": {
            "ADDR_NUM": 414,
            "ST_NAME": "GRANT",
            "ST_TYPE": "ST",
            "ZIP_CODE": "15219",
            "PARCELID": parcel,
            **overrides,
        },
        "geometry": {"x": -79.996, "y": 40.438},
    }


@pytest.mark.parametrize(
    "linked,boundary,expected",
    [
        ("SECOND", "SECOND", "SECOND"),
        ("", "SECOND", "SECOND"),
        ("SECOND", "", "SECOND"),
        ("UNRELATED", "UNRELATED", "0002J00002000000"),
    ],
)
async def test_county_evidence_ranks_only_exact_candidates(linked, boundary, expected):
    apis = candidates()
    apis.address_points = [address_point(linked)]
    apis.parcel_features = [{"attributes": {"PIN": boundary}}]
    result, ctx = await fetch(apis)
    e = next(e for e in result.evidence if e.provider == "wprdc_assessments")
    assert e.record_id == expected
    resolution = e.details["parcel_resolution"]
    assert resolution["uncertain"] == (expected != "SECOND")
    assert ctx.counts["api"] == 12
    permit_request = next(
        r for r in apis.requests if r.url.params.get("resource_id", "").startswith("2222")
    )
    assert json.loads(permit_request.url.params["filters"])["parcel_num"] == expected
    polygon_request = next(r for r in apis.requests if "/Parcels/" in r.url.path)
    assert json.loads(polygon_request.url.params["geometry"])["points"] == [[-79.996, 40.438]]
    assert polygon_request.url.params["spatialRel"] == "esriSpatialRelIntersects"


@pytest.mark.parametrize(
    "overrides",
    [
        {"ST_NAME": "OTHER"},
        {"ADDR_NUM": 415},
        {"ZIP_CODE": "00000"},
        {"UNIT": "2"},
        {"STATUS": "RETIRED"},
    ],
)
async def test_wrong_or_inactive_address_point_cannot_choose_parcel(overrides):
    apis = candidates()
    apis.address_points = [address_point(**overrides)]
    apis.parcel_features = [{"attributes": {"PIN": "SECOND"}}]
    result, _ = await fetch(apis)
    e = next(e for e in result.evidence if e.provider == "wprdc_assessments")
    assert e.record_id == "0002J00002000000"
    assert e.details["parcel_resolution"]["uncertain"]
    assert not any("/Parcels/" in r.url.path for r in apis.requests)


async def test_response_order_does_not_change_fallback_and_uncertainty_reaches_permits():
    apis = candidates()
    apis.assessments.reverse()
    result, _ = await fetch(apis)
    selected = [e for e in result.evidence if e.provider in {"wprdc_assessments", "wprdc_permits"}]
    assert len(selected) == 2
    assert all(
        e.details["parcel_resolution"]["selected_parcel_id"] == "0002J00002000000" for e in selected
    )
    assert all("uncertain" in e.excerpt.lower() for e in selected)
    from surreal_estate.synthesis.frontend import FrontendResponse

    bench = bench_response(
        FrontendResponse(report=RunReport(case=fixture_case(), result=result), web=[])
    )
    finding = next(f for f in bench["findings"] if f["topic"] == "property_assessment")
    assert "uncertain match" in finding["qualifier"]


async def test_gis_failure_does_not_block_assessments_or_permits():
    apis = candidates()
    apis.fail_provider = "gisdata.alleghenycounty.us"
    result, _ = await fetch(apis)
    assert all(c.status == "complete" for c in result.coverage)
    e = next(e for e in result.evidence if e.provider == "wprdc_assessments")
    assert e.details["parcel_resolution"]["checks"][-1]["status"] == "unavailable"


async def test_budget_reserved_for_other_sources():
    apis = candidates()
    result, ctx = await fetch(apis, Budget(max_api_calls=10))
    assert ctx.counts["api"] == 10
    assert all(c.status == "complete" for c in result.coverage)
    assert not any("gisdata" in r.url.host for r in apis.requests)


async def test_capped_candidates_still_select_with_explicit_limit():
    apis = candidates()
    apis.total_override = 100
    result, _ = await fetch(apis)
    e = next(e for e in result.evidence if e.provider == "wprdc_assessments")
    assert e.details["parcel_resolution"]["candidates_limited"]
    assert e.details["parcel_resolution"]["uncertain"]


async def test_arcgis_error_response_and_truncation_fall_back():
    for response in [
        {"error": {"code": 500}},
        {"features": [address_point()], "exceededTransferLimit": True},
    ]:
        apis = candidates()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r, payload=response: httpx.Response(200, json=payload)
            )
        ) as http:
            chosen, resolution = await resolve_parcel(
                http, RunContext(), apis.assessments, "414", "GRANT ST", "15219"
            )
        assert chosen == "0002J00002000000"
        assert resolution["uncertain"]


async def test_conflicting_gis_signals_keep_uncertainty():
    apis = candidates()
    apis.address_points = [address_point("SECOND")]
    apis.parcel_features = [{"attributes": {"PIN": "0002J00002000000"}}]
    result, _ = await fetch(apis)
    e = next(e for e in result.evidence if e.provider == "wprdc_assessments")
    assert e.record_id == "SECOND"
    assert e.details["parcel_resolution"]["uncertain"]
    assert "another candidate" in e.details["parcel_resolution"]["reason"]


async def test_duplicate_rows_with_same_parcel_do_not_trigger_gis():
    apis = PublicAPIs()
    apis.assessments.append({**apis.assessments[0], "CARDNUMBER": "2"})
    result, _ = await fetch(apis)
    assert not any("gisdata" in r.url.host for r in apis.requests)
    assert next(c for c in result.coverage if c.topic == "property_assessment").status == "complete"
