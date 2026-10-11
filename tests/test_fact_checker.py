import json
from datetime import timedelta

import httpx
import pytest

from surreal_estate.channels.web.channel import WebChannel
from surreal_estate.channels.web.fact_checker import FactChecker
from surreal_estate.evals.fixtures import fixture_case
from surreal_estate.llm.gemini import GroundedSearchClient
from surreal_estate.models import (
    FactCheckPlan,
    GroundedResponse,
    GroundingChunk,
    GroundingSupport,
    ResearchQuerySpec,
)
from surreal_estate.orchestrator.context import Budget, RunContext
from surreal_estate.policy.gate import PolicyDenied

CHECKS = [
    "location",
    "dates",
    "independent_sources",
    "contradictions",
    "opinion_vs_fact",
    "restaurant_identity",
    "distance",
    "review_freshness",
]


def restaurant_fixture():
    case = fixture_case().model_copy(update={"priorities": ["restaurant_reviews"]})
    spec = ResearchQuerySpec(
        topic="restaurant_reviews",
        geography=case.geography,
        start_date=case.as_of - timedelta(days=365),
        end_date=case.as_of,
        source_types=["reviews"],
        address_anchor=case.address,
    )
    response = GroundedResponse(
        provider="gemini_search",
        text="ORIGINAL_GROUNDED_CONTENT",
        chunks=[GroundingChunk(uri="https://www.yelp.com/biz/synthetic")],
        supports=[GroundingSupport(text="ORIGINAL_GROUNDED_CONTENT", chunk_indices=[0])],
        search_entry_point="<div>Search Suggestions</div>",
    )
    plan = FactCheckPlan(topic=spec.topic, geography=spec.geography, checks=CHECKS)
    return case, spec, response, plan


async def test_separate_nemotron_agent_never_receives_grounded_content():
    case, spec, original, plan = restaurant_fixture()
    ctx = RunContext()

    class Nemotron:
        async def generate(self, schema, system, payload, context):
            assert issubclass(schema, FactCheckPlan)
            assert "ORIGINAL_GROUNDED_CONTENT" not in payload
            assert json.loads(payload)["specification"]["address_anchor"] == case.address
            return plan

    class Search:
        async def recheck(self, query, response, checks, context):
            assert response is original
            assert checks == plan
            context.reserve("factcheck")
            return response

    result = await FactChecker(Nemotron(), Search()).recheck(case, spec, original, ctx)
    assert result is original
    assert ctx.counts["factcheck"] == 1


async def test_successful_search_recheck_labels_and_no_dossier_claims():
    case, spec, original, _ = restaurant_fixture()

    class Search:
        async def search(self, spec, ctx):
            return original

    class Checker:
        async def recheck(self, case, spec, response, ctx):
            ctx.reserve("factcheck")
            return original.model_copy(update={"text": "REFINED_CONTENT"})

    channel = WebChannel([spec], Search(), fact_checker=Checker())
    result = await channel.run(case, RunContext())
    assert result.coverage[0].status == "complete"
    assert result.coverage[0].reason == "Search completed · displayed separately"
    assert result.coverage[1].channel == "fact_checker"
    assert len(channel.displays) == 2
    assert channel.displays[1].stage == "Claim re-check · model assessment"
    assert not result.observations and not result.evidence


async def test_factcheck_failure_preserves_original_search():
    case, spec, original, _ = restaurant_fixture()

    class Search:
        async def search(self, spec, ctx):
            return original

    class Checker:
        async def recheck(self, *args):
            raise TimeoutError()

    channel = WebChannel([spec], Search(), fact_checker=Checker())
    result = await channel.run(case, RunContext())
    assert result.coverage[0].status == "complete"
    assert result.coverage[1].status == "truncated"
    assert len(channel.displays) == 1


async def test_no_factcheck_calls_for_empty_search():
    case, spec, original, _ = restaurant_fixture()

    class Search:
        async def search(self, spec, ctx):
            return original.model_copy(update={"supports": []})

    class Checker:
        async def recheck(self, *args):
            raise AssertionError("Empty search must not spend verification budget")

    result = await WebChannel([spec], Search(), fact_checker=Checker()).run(case, RunContext())
    assert result.coverage[0].status == "empty"


def test_restaurant_scope_and_factcheck_plan_fail_closed():
    case, spec, _, plan = restaurant_fixture()
    ctx = RunContext()
    ctx.policy.query(spec, case)
    with pytest.raises(PolicyDenied):
        ctx.policy.query(spec.model_copy(update={"address_anchor": "wrong address"}), case)
    with pytest.raises(PolicyDenied):
        ctx.policy.factcheck(plan.model_copy(update={"checks": CHECKS[:3]}), spec, case)
    with pytest.raises(PolicyDenied):
        ctx.policy.factcheck(
            plan.model_copy(update={"geography": "Pittsburgh, Kansas"}), spec, case
        )


async def test_factcheck_budget_checked_before_local_generation():
    case, spec, original, _ = restaurant_fixture()
    from surreal_estate.orchestrator.context import BudgetExceeded

    with pytest.raises(BudgetExceeded):
        await FactChecker(None, None).recheck(
            case, spec, original, RunContext(budget=Budget(max_factcheck_calls=0))
        )


async def test_semantic_restaurant_search_and_opinion_preserving_refinement():
    case, spec, original, plan = restaurant_fixture()
    ctx = RunContext()
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        search = GroundedSearchClient(http, api_key="test-key")
        await search.search(spec, ctx)
        await search.recheck(spec, original, plan, ctx)
    first = requests[0]["contents"][0]["parts"][0]["text"]
    second = requests[1]["contents"][0]["parts"][0]["text"]
    assert case.address in first
    assert spec.max_queries == 3 and plan.max_queries == 3
    assert '"radius_meters":1000' in first
    assert "in the immediate vicinity of the address_anchor" in first
    assert "general restaurant reviews, local food publications, or Google Reviews" in first
    assert "recent review themes" in first
    assert (
        "general summary of the restaurant's reputation based on available search results" in first
    )
    for prompt in (first, second):
        assert "site:yelp.com" not in prompt
        assert "at most one search query" not in prompt
        assert "no accessible Yelp review evidence found" not in prompt
    assert "Do not reject or discard an opinion" in second
    assert "Split mixed statements into factual components" in second
    assert "ORIGINAL_GROUNDED_CONTENT" in second
    assert "corroborated, contradicted" in second
    assert requests[1]["tools"] == [{"google_search": {}}]
    assert ctx.counts["grounded"] == 1 and ctx.counts["factcheck"] == 1


def test_multiple_internal_queries_do_not_consume_multiple_application_calls():
    from surreal_estate.models import ResearchPlan

    case, spec, _, _ = restaurant_fixture()
    case = case.model_copy(update={"priorities": ["restaurant_reviews", "neighborhood_discussion"]})
    discussion = spec.model_copy(
        update={"topic": "neighborhood_discussion", "source_types": ["discussion"]}
    )
    plan = ResearchPlan(channels=["web"], queries=[spec, discussion])
    ctx = RunContext()
    ctx.policy.plan(plan, case, 2)
    with pytest.raises(PolicyDenied):
        ctx.policy.plan(plan, case, 1)


async def test_opinion_only_recheck_is_preserved_in_display():
    case, spec, original, _ = restaurant_fixture()
    opinion = original.model_copy(
        update={"text": "Opinion: reviewers describe the atmosphere as cozy."}
    )

    class Search:
        async def search(self, spec, ctx):
            return original

    class Checker:
        async def recheck(self, case, spec, response, ctx):
            ctx.reserve("factcheck")
            return opinion

    channel = WebChannel([spec], Search(), fact_checker=Checker())
    result = await channel.run(case, RunContext())
    assert result.coverage[1].status == "complete"
    assert channel.displays[1].response.text == opinion.text
    assert not result.observations  # Opinions remain displayed assessments, not verified facts.


async def test_factcheck_completes_checklist_without_changing_scope():
    case, spec, original, plan = restaurant_fixture()
    ctx = RunContext()

    class Nemotron:
        async def generate(self, *args):
            return plan.model_copy(update={"checks": ["location", "location", "opinion_vs_fact"]})

    class Search:
        async def recheck(self, query, response, effective_plan, context):
            assert effective_plan.topic == plan.topic
            assert effective_plan.geography == plan.geography
            assert set(effective_plan.checks) == set(CHECKS)
            assert len(effective_plan.checks) == len(CHECKS)
            return response

    await FactChecker(Nemotron(), Search()).recheck(case, spec, original, ctx)
    event = ctx.debug.events[0]
    assert event.request["model_plan"]["checks"].count("location") == 2
    assert "distance" in event.parsed["added_required_checks"]
    assert event.parsed["decision"] == "allowed"
