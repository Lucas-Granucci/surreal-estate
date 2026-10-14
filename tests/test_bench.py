import json

import pytest
from test_frontend import outcome_fixture
from test_webapp import confirmed_request, fixture_executor, request, wait_for_job

from surreal_estate.models import Coverage, Evidence, Observation
from surreal_estate.synthesis.frontend import build_frontend_response, save_development_snapshot
from surreal_estate.webapp.display import bench_response
from surreal_estate.webapp.server import App, capabilities


def test_idempotent_generation_survives_restart_and_rejects_changed_scope(tmp_path):
    app = App(tmp_path, fixture_executor)
    first = confirmed_request(app)
    first.request_id = "same-request-123"
    retry = first.model_copy(deep=True)
    job = app.start(first)
    wait_for_job(app, job["id"])
    restored = App(tmp_path, fixture_executor)
    assert restored.start(retry)["id"] == job["id"]
    assert len(restored.jobs) == 1
    retry.address = "999 Other Street"
    with pytest.raises(RuntimeError, match="already used"):
        restored.start(retry)


def test_import_old_snapshot_is_additive_and_idempotent(tmp_path):
    source = save_development_snapshot(outcome_fixture(), path=str(tmp_path / "legacy.json"))
    original = source.read_bytes()
    app = App(tmp_path, fixture_executor)
    assert len(app.jobs) == 1
    identifier = next(iter(app.jobs))
    assert app.jobs[identifier]["imported"]
    assert app.outcome(identifier).displays
    assert len(App(tmp_path).jobs) == 1
    assert source.read_bytes() == original


def test_normalization_preserves_sources_web_and_unknown_fields_in_raw_transport():
    payload = build_frontend_response(outcome_fixture())
    before = payload.model_dump_json()
    bench = bench_response(payload)
    assert payload.model_dump_json() == before
    assert bench["evidence"] == payload.model_dump(mode="json")["report"]["result"]["evidence"]
    assert [w["response"] for w in bench["web"]] == [
        w.model_dump(mode="json")["response"] for w in payload.web
    ]
    assert all(
        f["qualifier"].startswith("AI-assisted") for f in bench["findings"] if f["web_indices"]
    )


def test_legacy_observation_and_empty_blocked_sources_stay_distinct():
    payload = build_frontend_response(outcome_fixture())
    e = Evidence(
        provider="openstreetmap",
        uri="https://example.org",
        title="Old mapped place",
        excerpt="Mapped place",
        retention="persistent",
        kind="reported",
    )
    payload.report.result.evidence = [e]
    payload.report.result.observations = [
        Observation(
            topic="mapped_amenities",
            statement="Old returned place",
            evidence_ids=[e.id],
            location_scope="Pittsburgh",
            observed_on="2026-01-01",
            qualifier="reported",
            confidence=0.8,
        )
    ]
    payload.report.result.coverage = [
        Coverage(
            channel="apis", topic="building_permits", status="blocked", reason="No unique parcel"
        ),
        Coverage(
            channel="apis", topic="street_closures", status="empty", reason="No returned records"
        ),
        Coverage(
            channel="listing",
            topic="research",
            status="blocked",
            reason="Not selected for this run",
        ),
    ]
    payload.web = []
    bench = bench_response(payload)
    by_topic = {f["topic"]: f for f in bench["findings"]}
    assert by_topic["mapped_amenities"]["statements"] == ["Old returned place"]
    assert by_topic["building_permits"]["unresolved"]
    assert not by_topic["street_closures"]["unresolved"]
    assert "research" not in by_topic


def test_capabilities_missing_key_is_unavailable_without_network(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert capabilities() == {"apis": {"available": True}, "web": {"available": False}}


def test_bench_api_keeps_sources_and_safe_model_html(tmp_path):
    outcome = outcome_fixture()
    outcome.displays[0].response.text = "<script>alert(1)</script> [bad](javascript:alert(1))"
    save_development_snapshot(outcome, path=str(tmp_path / "old.json"))
    app = App(tmp_path)
    identifier = next(iter(app.jobs))
    headers, body = request(app, f"/reports/{identifier}/bench.json")
    assert b"200 OK" in headers
    bench = json.loads(body)
    assert "<script>" not in bench["web"][0]["rendered_html"]
    assert 'href="javascript:' not in bench["web"][0]["rendered_html"]
    assert bench["web"][0]["response"]["text"].startswith("<script>")
    from surreal_estate.synthesis.frontend import DevelopmentSnapshot

    headers, body = request(app, f"/reports/{identifier}/source.json")
    assert b"200 OK" in headers
    assert DevelopmentSnapshot.model_validate_json(body).report.id == outcome.report.id


def test_stopped_stage_never_becomes_success():
    from surreal_estate.orchestrator.context import RunContext

    ctx = RunContext()
    ctx.trace = ["channel:web:started", "channel:web:stopped"]
    job = {"status": "complete", "channels": ["web"], "stage": "report"}
    states = {s["id"]: s["state"] for s in App.progress(job, ctx)["steps"]}
    assert states["web"] == "stopped"
    assert states["report"] == "done"


async def test_explicit_topics_complete_a_planner_omission_without_expanding_scope():
    from surreal_estate.evals.fixtures import (
        FixtureAPI,
        FixturePlanner,
        FixtureSearch,
        fixture_case,
    )
    from surreal_estate.orchestrator.context import RunContext
    from surreal_estate.orchestrator.runner import run

    class TrackingSearch(FixtureSearch):
        def __init__(self):
            super().__init__()
            self.topics = []

        async def search(self, spec, ctx):
            self.topics.append(spec.topic)
            response = await super().search(spec, ctx)
            return response.model_copy(
                update={"provider": "gemini_search", "search_entry_point": "<div>Suggestions</div>"}
            )

    search = TrackingSearch()
    case = fixture_case().model_copy(
        update={"priorities": ["neighborhood_discussion", "restaurant_reviews"]}
    )
    outcome = await run(
        case, RunContext(), FixturePlanner(), FixtureAPI(), search=search, selected_channels=["web"]
    )
    assert {q.topic for q in outcome.report.plan.queries} == set(case.priorities)
    assert all(
        q.address_anchor == case.address
        for q in outcome.report.plan.queries
        if q.topic == "restaurant_reviews"
    )
    assert len(outcome.report.plan.queries) == 2
    assert search.topics == ["neighborhood_discussion", "restaurant_reviews"]


async def test_one_web_topic_failure_does_not_suppress_the_next():
    import httpx

    from surreal_estate.channels.web.channel import WebChannel
    from surreal_estate.evals.fixtures import FixturePlanner, FixtureSearch, fixture_case
    from surreal_estate.orchestrator.context import RunContext

    case = fixture_case().model_copy(
        update={"priorities": ["neighborhood_discussion", "restaurant_reviews"]}
    )
    ctx = RunContext()
    first = (await FixturePlanner().plan(case, ctx)).queries[0]
    second = first.model_copy(
        update={
            "topic": "restaurant_reviews",
            "source_types": ["reviews"],
            "address_anchor": case.address,
        }
    )

    class Search(FixtureSearch):
        async def search(self, spec, ctx):
            if spec.topic == "neighborhood_discussion":
                raise httpx.ConnectError("PRIVATE transport error")
            response = await super().search(spec, ctx)
            return response.model_copy(
                update={"provider": "gemini_search", "search_entry_point": "<div>Suggestions</div>"}
            )

    channel = WebChannel([first, second], Search())
    result = await channel.run(case, ctx)
    assert [(c.topic, c.status) for c in result.coverage] == [
        ("neighborhood_discussion", "error"),
        ("restaurant_reviews", "complete"),
    ]
    assert "PRIVATE" not in result.model_dump_json()
    assert channel.displays[0].topic == "restaurant_reviews"
