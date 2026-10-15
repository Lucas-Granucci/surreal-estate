import asyncio
import json
from dataclasses import asdict

import httpx
import pytest

from surreal_estate.channels.web.planner import Planner
from surreal_estate.evals.fixtures import FixtureAPI, FixturePlanner, fixture_case
from surreal_estate.llm.nemotron import NemotronClient
from surreal_estate.llm.tavily import TavilyClient
from surreal_estate.orchestrator.context import Budget, RunContext
from surreal_estate.orchestrator.runner import run
from surreal_estate.store.sqlite import Store
from surreal_estate.synthesis.debug_view import render_debug


async def test_nemotron_exact_request_response_and_parsed_handoff():
    ctx = RunContext()
    plan = await FixturePlanner().plan(fixture_case(), ctx)
    sent = []
    body = {"done": True, "message": {"content": plan.model_dump_json()}, "eval_count": 32}

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await Planner(NemotronClient(http)).plan(fixture_case(), ctx)
    event = ctx.debug.events[0]
    assert event.request["body"] == sent[0]
    assert event.response == body
    assert event.parsed == plan.model_dump(mode="json")
    assert event.status == "complete"
    assert event.http_status == 200


async def test_debug_http_error_retains_redacted_response():
    ctx = RunContext()
    spec = (await FixturePlanner().plan(fixture_case(), ctx)).queries[0]
    secret = "synthetic-secret-key"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403, json={"error": {"message": "rejected " + secret}, "api_key": secret}
            )
        )
    ) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await TavilyClient(http, api_key=secret).search_sources("local research", spec, ctx)
    event = ctx.debug.events[0]
    assert event.status == "error"
    assert event.http_status == 403
    assert secret not in json.dumps(asdict(event))
    assert "[REDACTED]" in event.response["error"]["message"]
    assert "headers" not in event.request


async def test_timeout_closes_debug_event():
    ctx = RunContext(budget=Budget(request_seconds=0.01))
    spec = (await FixturePlanner().plan(fixture_case(), ctx)).queries[0]

    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TimeoutError):
            await TavilyClient(http, api_key="fake").search_sources("local research", spec, ctx)
    assert ctx.debug.events[0].status == "error"
    assert ctx.debug.events[0].error == "TimeoutError"


async def test_invalid_model_json_remains_inspectable():
    ctx = RunContext()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"done": True, "message": {"content": "invalid output"}}
            )
        )
    ) as http:
        with pytest.raises(ValueError):
            await Planner(NemotronClient(http)).plan(fixture_case(), ctx)
    event = ctx.debug.events[0]
    assert event.status == "error"
    assert event.response["message"]["content"] == "invalid output"
    assert event.parsed["validation_errors"][0]["type"] == "json_invalid"


async def test_debug_does_not_enter_store(tmp_path):
    ctx = RunContext()
    event = ctx.debug.begin(
        "fixture", {"body": {"contents": [{"parts": [{"text": "PRIVATE-DEBUG"}]}]}}
    )
    event.response = {"text": "PRIVATE-RESPONSE"}
    ctx.debug.finish(event)
    outcome = await run(fixture_case(), ctx, FixturePlanner(), FixtureAPI())
    store = Store(str(tmp_path / "runs.db"))
    store.save(outcome.report, ctx.policy)
    persisted = store.load(outcome.report.id).model_dump_json()
    assert "PRIVATE-DEBUG" not in persisted and "PRIVATE-RESPONSE" not in persisted
    assert len(outcome.debug_events) == 2
    store.close()


async def test_rejected_policy_decision_is_inspectable():
    ctx = RunContext(budget=Budget(max_web_topics=0))
    outcome = await run(fixture_case(), ctx, FixturePlanner(), FixtureAPI())
    event = outcome.debug_events[0]
    assert event.stage == "Policy gate"
    assert event.status == "error"
    assert event.parsed["decision"] == "blocked"
    assert len(event.request["plan"]["queries"]) == 1


def test_debug_html_escapes_provider_content():
    ctx = RunContext()
    event = ctx.debug.begin(
        "Nemotron", {"body": {"messages": [{"role": "user", "content": "<script>bad()</script>"}]}}
    )
    event.response = {"message": {"content": "<img src=x onerror=bad()>"}}
    ctx.debug.finish(event, parsed={"plan": "example"})
    html = render_debug(ctx.debug.events)
    assert "<script>" not in html and "<img src=" not in html
    assert "&lt;script&gt;" in html
    assert "Full response JSON" in html
    assert "Parsed output / handoff" in html
