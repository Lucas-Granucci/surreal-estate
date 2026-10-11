import json

import httpx
import pytest

from surreal_estate.channels.apis.census import CensusGeocoder
from surreal_estate.channels.web.planner import Planner
from surreal_estate.evals.fixtures import FixturePlanner, fixture_case
from surreal_estate.llm.gemini import GroundedSearchClient, parse_response
from surreal_estate.llm.nemotron import NemotronClient
from surreal_estate.orchestrator.context import Budget, BudgetExceeded, RunContext


async def test_ollama_schema_planning_request():
    ctx = RunContext()
    plan = await FixturePlanner().plan(fixture_case(), ctx)

    def handler(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "nemotron-3-nano:4b"
        assert body["format"]["type"] == "object"
        assert not body["stream"]
        payload = json.loads(body["messages"][1]["content"])
        assert payload["query_window"]["end_date"] == fixture_case().as_of.isoformat()
        assert payload["query_window"]["start_date"] < payload["query_window"]["end_date"]
        return httpx.Response(
            200, json={"done": True, "message": {"content": plan.model_dump_json()}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await Planner(NemotronClient(http)).plan(fixture_case(), ctx)
    assert result == plan
    assert ctx.counts["llm"] == 1


async def test_incomplete_ollama_json_fails_closed():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"done": True, "done_reason": "length", "message": {"content": "{}"}}
            )
        )
    ) as http:
        with pytest.raises(ValueError, match="Incomplete"):
            await Planner(NemotronClient(http)).plan(fixture_case(), RunContext())


async def test_gemini_request_no_json_mode_and_preserves_metadata():
    ctx = RunContext()
    spec = (await FixturePlanner().plan(fixture_case(), ctx)).queries[0]

    def handler(request):
        body = json.loads(request.content)
        assert body["tools"] == [{"google_search": {}}]
        assert "responseMimeType" not in body["generationConfig"]
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "test-key" not in str(request.url)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [{"text": "hidden", "thought": True}, {"text": "Answer"}]
                        },
                        "groundingMetadata": {
                            "groundingChunks": [
                                {"retrievedContext": {}},
                                {"web": {"uri": "https://example.org", "title": "Example"}},
                            ],
                            "groundingSupports": [
                                {
                                    "segment": {"text": "Answer", "endIndex": 6},
                                    "groundingChunkIndices": [1],
                                }
                            ],
                            "searchEntryPoint": {"renderedContent": "<div>Suggestions</div>"},
                            "webSearchQueries": ["q"],
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await GroundedSearchClient(http, "test-key").search(spec, ctx)
    assert result.text == "Answer"
    assert len(result.chunks) == 2 and result.chunks[0].uri is None
    assert result.supports[0].chunk_indices == [1]
    assert result.search_entry_point == "<div>Suggestions</div>"
    assert not result.truncated


def test_empty_gemini_candidates_are_honest_empty():
    assert parse_response({"promptFeedback": {"blockReason": "SAFETY"}}).text == ""


@pytest.mark.parametrize("matches, status", [([], "empty"), ([{}, {}], "blocked")])
async def test_census_no_match_and_ambiguous_match(matches, status):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"result": {"addressMatches": matches}})
        )
    ) as http:
        result = await CensusGeocoder(http).run(fixture_case(), RunContext())
    assert result.coverage[0].status == status
    assert not result.observations


async def test_census_records_single_match_and_request_provenance():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "result": {
                        "addressMatches": [
                            {
                                "matchedAddress": "414 GRANT ST, PITTSBURGH, PA",
                                "coordinates": {"x": -79.996, "y": 40.438},
                            }
                        ]
                    }
                },
            )
        )
    ) as http:
        result = await CensusGeocoder(http).run(fixture_case(), RunContext())
    assert result.observations[0].qualifier == "official_record"
    assert "address=" in str(result.evidence[0].uri)
    assert "address_range_interpolation" in result.observations[0].flags


def test_call_budget_is_reserved_before_dispatch():
    ctx = RunContext(budget=Budget(max_grounded_calls=1))
    ctx.reserve("grounded")
    with pytest.raises(BudgetExceeded):
        ctx.reserve("grounded")
    assert ctx.counts["grounded"] == 1
