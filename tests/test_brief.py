import json

import httpx
import pytest
from pydantic import ValidationError
from test_tavily import finding, source, spec_fixture

from surreal_estate.channels.web.research import ResearchAgent, ResearchDraft, SearchTasks
from surreal_estate.llm.brief import GeminiBriefWriter
from surreal_estate.models import ChannelResult, RunReport, WebResearch
from surreal_estate.orchestrator.context import Budget, BudgetExceeded, RunContext
from surreal_estate.orchestrator.runner import RunOutcome
from surreal_estate.policy.gate import PolicyGate
from surreal_estate.store.export import build_export
from surreal_estate.synthesis.frontend import (
    build_frontend_response,
    load_snapshot_outcome,
    save_development_snapshot,
)
from surreal_estate.webapp.display import bench_response


def answer(ref="S1:P1"):
    return {"overview": {"text": "A discussion mentions evening bus service; address relevance remains uncertain.",
        "source_refs": [ref]}, "sections": [{"heading": "Evening transport", "paragraphs": [
            {"text": "The returned discussion describes evening buses as a concern, rather than a verified service assessment.",
             "source_refs": [ref]}]}], "limitations": ["Only one discussion was supplied."],
        "follow_up_questions": []}


async def make_brief(body=None):
    case, spec = spec_fixture()
    e = source()
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=body or {"candidates": [{"finishReason": "STOP",
            "content": {"parts": [{"text": json.dumps(answer())}]}}],
            "usageMetadata": {"promptTokenCount": 100}})
    ctx = RunContext()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        brief = await GeminiBriefWriter(http, "SECRET").write(case, spec,
            WebResearch(topic=spec.topic, evidence_ids=[e.id]), [e], ctx)
    return brief, e, ctx, requests


async def test_writer_has_no_tools_and_uses_only_supplied_source_refs():
    brief, e, ctx, requests = await make_brief()
    body = requests[0]
    assert "tools" not in body and "toolConfig" not in body
    assert "google_search" not in json.dumps(body)
    assert body["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
    assert brief.overview.citations[0].evidence_id == e.id
    assert brief.overview.citations[0].excerpt == e.excerpt
    assert ctx.counts == {"synthesis": 1}
    assert "SECRET" not in repr(ctx.debug.events)


@pytest.mark.parametrize("candidate", [
    {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}},
    {"finishReason": "STOP", "groundingMetadata": {"webSearchQueries": ["unexpected"]}},
    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(answer("invented"))}]}},
])
async def test_truncated_grounded_or_unknown_citation_responses_are_rejected(candidate):
    with pytest.raises(ValueError):
        await make_brief({"candidates": [candidate]})


async def test_brief_survives_snapshot_export_and_bench_projection(tmp_path):
    brief, e, _, _ = await make_brief()
    case, spec = spec_fixture()
    research = WebResearch(topic=spec.topic, brief=brief, summary=brief.overview.text,
        synthesis_status="complete", evidence_ids=[e.id])
    report = RunReport(case=case, result=ChannelResult(evidence=[e], research=[research]))
    path = save_development_snapshot(RunOutcome(report, []), path=str(tmp_path / "brief.json"))
    restored = load_snapshot_outcome(str(path))
    assert restored.report.result.research[0].brief == brief
    assert build_export(report, PolicyGate()).report.result.research[0].brief == brief
    bench = bench_response(build_frontend_response(restored))
    assert bench["research"][0]["brief"]["overview"]["ui_id"].startswith("brief-")
    # An export cannot retain a brief whose cited material was excluded.
    e.retention = "ephemeral"
    exported = build_export(report, PolicyGate())
    assert exported.report.result.research[0].brief is None
    assert exported.report.result.research[0].summary == ""


async def test_missing_brief_source_fails_report_validation():
    brief, _, _, _ = await make_brief()
    with pytest.raises(ValidationError):
        ChannelResult(research=[WebResearch(topic="neighborhood_discussion", brief=brief)])


async def test_writing_failure_preserves_local_findings_and_sources():
    case, spec = spec_fixture()
    e = source()
    class Search:
        async def search_sources(self, *args, **kwargs):
            return [e], 1
    class Local:
        async def generate(self, schema, *args):
            return SearchTasks(queries=["Pittsburgh transit"]) if schema is SearchTasks else ResearchDraft(findings=[finding(e)])
    class FailedWriter:
        async def write(self, *args):
            raise TimeoutError()
    result = await ResearchAgent(Local(), Search(), FailedWriter()).research(case, spec, RunContext())
    assert result.research[0].synthesis_status == "error"
    assert result.evidence and result.research[0].findings
    assert result.coverage[0].status == "truncated"


async def test_synthesis_has_a_separate_bounded_budget():
    case, spec = spec_fixture()
    e = source()
    async with httpx.AsyncClient() as http:
        with pytest.raises(BudgetExceeded):
            await GeminiBriefWriter(http, "SECRET").write(case, spec,
                WebResearch(topic=spec.topic), [e], RunContext(budget=Budget(max_synthesis_calls=0)))


async def test_invalid_writer_output_gets_one_bounded_format_repair():
    case, spec = spec_fixture()
    e = source()
    invalid = answer()
    invalid["overview"]["source_refs"] = ["S1:P1"] * 9
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        result = invalid if len(requests) == 1 else answer()
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP",
            "content": {"parts": [{"text": json.dumps(result)}]}}]})
    ctx = RunContext()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        brief = await GeminiBriefWriter(http, "SECRET").write(case, spec,
            WebResearch(topic=spec.topic, evidence_ids=[e.id]), [e], ctx)
    assert brief.overview.text == answer()["overview"]["text"]
    assert len(requests) == 2
    assert ctx.counts == {"synthesis": 2}
    assert all("tools" not in request for request in requests)


async def test_repeated_invalid_output_stops_with_safe_explanation():
    from surreal_estate.errors import BriefResponseError, failure_reason
    invalid = answer()
    invalid["overview"]["source_refs"] = []
    with pytest.raises(BriefResponseError) as error:
        await make_brief({"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps(invalid)}]}}]})
    assert "format or citation constraints" in failure_reason(error.value)
