import asyncio
from datetime import timedelta

import pytest

from surreal_estate.channels.web.verifier import verify
from surreal_estate.evals.fixtures import (
    FixtureAPI,
    FixtureExtractor,
    FixturePlanner,
    FixtureSearch,
    fixture_case,
)
from surreal_estate.models import ChannelResult, Coverage, Evidence, Observation, RunReport
from surreal_estate.orchestrator.context import Budget, RunContext
from surreal_estate.orchestrator.runner import run
from surreal_estate.policy.gate import PolicyDenied, PolicyGate
from surreal_estate.store.sqlite import Store
from surreal_estate.synthesis.dossier import render_markdown, synthesize


async def setup_fixture():
    case, ctx = fixture_case(), RunContext()
    plan = await FixturePlanner().plan(case, ctx)
    response = await FixtureSearch().search(plan.queries[0], ctx)
    extraction = await FixtureExtractor().extract(plan.queries[0], response, ctx)
    return case, ctx, plan, response, extraction


async def test_end_to_end_durable_synthetic_demo(tmp_path):
    case, ctx = fixture_case(), RunContext()
    outcome = await run(
        case,
        ctx,
        FixturePlanner(),
        FixtureAPI(),
        search=FixtureSearch(),
        extractor=FixtureExtractor(),
        demo=True,
    )
    assert len(outcome.report.claims) == 1
    assert "single_source" in outcome.report.claims[0].flags
    assert "SYNTHETIC DEMO" in render_markdown(outcome.report)
    store = Store(str(tmp_path / "runs.db"))
    store.save(outcome.report, ctx.policy)
    loaded = store.load(outcome.report.id)
    assert loaded.claims == outcome.report.claims
    store.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_geo",
        "old_date",
        "future_date",
        "no_support",
        "negative_index",
        "bad_chunk",
        "fabricated",
        "wrong_topic",
        "unsafe",
        "unsupported_geo",
    ],
)
async def test_verifier_rejects_unsubstantiated_observations(mutation):
    case, ctx, plan, response, extraction = await setup_fixture()
    observation = extraction.observations[0]
    if mutation == "wrong_geo":
        observation.location_scope = "Pittsburgh, Kansas"
    elif mutation == "old_date":
        observation.observed_on = plan.queries[0].start_date - timedelta(days=1)
    elif mutation == "future_date":
        observation.observed_on = case.as_of + timedelta(days=1)
    elif mutation == "no_support":
        response.supports = []
    elif mutation == "negative_index":
        observation.support_indices = [-1]
    elif mutation == "bad_chunk":
        response.supports[0].chunk_indices = [99]
    elif mutation == "fabricated":
        observation.statement = "Unrelated invented statement"
    elif mutation == "wrong_topic":
        observation.topic = "road_projects"
    elif mutation == "unsafe":
        observation.statement = "This is a safe neighborhood."
    elif mutation == "unsupported_geo":
        response.supports[0].text = response.text = observation.statement = (
            "Sidewalk work reported."
        )
    result = verify(plan.queries[0], response, extraction, ctx.policy)
    assert result.observations == []
    assert result.coverage[0].status == "empty"


async def test_plan_over_budget_does_not_call_channels():
    class ExplodingAPI:
        async def run(self, *args):
            raise AssertionError("should never run")

    outcome = await run(
        fixture_case(),
        RunContext(budget=Budget(max_web_topics=0)),
        FixturePlanner(),
        ExplodingAPI(),
    )
    assert outcome.report.result.coverage[0].status == "blocked"
    assert not outcome.report.result.observations


async def test_timeout_returns_coverage():
    class SlowPlanner:
        async def plan(self, *args):
            await asyncio.sleep(1)

    outcome = await run(
        fixture_case(),
        RunContext(budget=Budget(deadline_seconds=0.01)),
        SlowPlanner(),
        FixtureAPI(),
    )
    assert outcome.report.result.coverage[0].status == "error"
    assert "TimeoutError" in outcome.report.result.coverage[0].reason






def test_store_blocks_ephemeral_evidence_and_derived_claims(tmp_path):
    evidence = Evidence(
        provider="gemini_search",
        uri="https://example.org/private",
        title="SECRET",
        excerpt="SECRET",
        retention="persistent",
        kind="reported",
    )
    observation = Observation(
        topic="discussion",
        statement="SECRET",
        evidence_ids=[evidence.id],
        location_scope="Pittsburgh",
        observed_on=fixture_case().as_of,
        qualifier="reported",
        confidence=0.8,
    )
    result = ChannelResult(
        evidence=[evidence],
        observations=[observation],
        coverage=[Coverage(channel="web", topic="discussion", status="attempted", reason="SECRET")],
    )
    report = RunReport(
        case=fixture_case(), result=result, claims=synthesize(result), trace=["SECRET"]
    )
    store = Store(str(tmp_path / "test.db"))
    store.save(report, PolicyGate())
    loaded = store.load(report.id)
    assert "SECRET" not in loaded.model_dump_json()
    assert not loaded.claims
    store.close()


def test_provenance_dangling_reference_rejected():
    with pytest.raises(ValueError):
        ChannelResult(
            observations=[
                Observation(
                    topic="x",
                    statement="x",
                    evidence_ids=["missing"],
                    location_scope="x",
                    observed_on=fixture_case().as_of,
                    qualifier="reported",
                    confidence=1,
                )
            ]
        )


def test_unknown_provider_and_spoofed_official_host_are_not_persistable():
    evidence = Evidence(
        provider="census",
        uri="https://example.org/",
        title="x",
        excerpt="x",
        retention="persistent",
        kind="official_record",
    )
    assert not PolicyGate().persistable(evidence)
    with pytest.raises(PolicyDenied):
        PolicyGate().require("unknown")
