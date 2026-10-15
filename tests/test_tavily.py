import json

import httpx
import pytest

from surreal_estate.channels.web.channel import WebChannel
from surreal_estate.channels.web.research import ResearchAgent, ResearchDraft, SearchTasks
from surreal_estate.evals.fixtures import fixture_case
from surreal_estate.llm.tavily import TavilyClient, public_url
from surreal_estate.models import (
    ChannelResult,
    Coverage,
    Evidence,
    ResearchQuerySpec,
    RunReport,
    WebCitation,
    WebFinding,
    WebResearch,
)
from surreal_estate.orchestrator.context import Budget, RunContext
from surreal_estate.orchestrator.runner import RunOutcome
from surreal_estate.policy.gate import PolicyGate
from surreal_estate.store.export import build_export
from surreal_estate.synthesis.frontend import (
    build_frontend_response,
    load_snapshot_outcome,
    save_development_snapshot,
)
from surreal_estate.webapp.display import bench_response


def spec_fixture():
    case = fixture_case()
    return case, ResearchQuerySpec(topic="neighborhood_discussion", geography=case.geography,
        address_anchor=case.address, start_date="2025-01-01", end_date="2026-01-01",
        source_types=["discussion"])


def source(content="People discuss late evening bus service.", uri="https://example.org/thread"):
    return Evidence(provider="tavily_search", uri=uri, title="Local thread", excerpt=content,
        retention="persistent", kind="reported", details={"content": content,
        "content_kind": "search_passage", "topic": "neighborhood_discussion"})


def finding(e, **updates):
    return WebFinding(title="Evening transit discussions", statement="A discussion mentions evening buses.",
        kind="opinion", citations=[WebCitation(evidence_id=e.id, excerpt=e.excerpt)], **updates)


@pytest.mark.parametrize("url", ["http://localhost/a", "http://127.0.0.1/a", "https://10.0.0.1",
    "https://user:pass@example.org/a", "file:///tmp/a", "http://169.254.169.254", "http://host.internal"])
def test_private_and_credential_urls_rejected(url):
    assert not public_url(url)


async def test_search_returns_source_material_not_provider_answer(monkeypatch):
    monkeypatch.setenv("TAVILY_SEARCH_DEPTH", "basic")
    _case, spec = spec_fixture()
    requests = []
    def handle(request):
        assert request.url.host == "api.tavily.com"
        body = json.loads(request.content)
        requests.append(body)
        assert body["include_answer"] is False
        assert request.headers["Authorization"] == "Bearer SECRET"
        return httpx.Response(200, json={"answer": "UNTRUSTED ANSWER", "results": [
            {"url": "https://example.org/thread", "title": "Thread", "content": "Snippet",
             "raw_content": "Actual page content", "published_date": "2025-12-01"},
            {"url": "http://127.0.0.1/secret", "content": "Private"},
        ], "usage": {"credits": 1}})
    ctx = RunContext()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        sources, credits = await TavilyClient(http, "SECRET").search_sources("Pittsburgh", spec, ctx)
    assert len(sources) == 1 and credits == 1
    assert sources[0].details["content"] == "Snippet\n\nActual page content"
    assert sources[0].source_updated_at == "2025-12-01"
    assert "UNTRUSTED ANSWER" not in sources[0].model_dump_json()
    assert "SECRET" not in repr(ctx.debug.events)
    assert ctx.counts["web_search"] == 1
    assert "start_date" not in requests[0]  # Undated opinions remain discoverable.


async def test_channel_uses_nemotron_and_preserves_supported_undated_opinions():
    case, spec = spec_fixture()
    e = source()
    class Search:
        provider = "tavily_search"
        async def search_sources(self, *args, **kwargs):
            return [e], 1
    class Local:
        async def generate(self, schema, system, data, ctx):
            if schema is SearchTasks:
                return SearchTasks(queries=["evening transit"])
            assert "S1:P1" in data
            return ResearchDraft(findings=[finding(e), finding(e).model_copy(update={
                "citations": [WebCitation(evidence_id=e.id, excerpt="Invented quote")]
            })])
    search = Search()
    channel = WebChannel([spec], search, extractor=ResearchAgent(Local(), search))
    result = await channel.run(case, RunContext())
    assert len(result.research[0].findings) == 1
    assert not channel.displays
    assert any("publication date" in x for x in result.research[0].limitations)
    assert any("unsupported" in x for x in result.research[0].limitations)
    assert result.coverage[0].provider == "tavily_search"


async def test_review_corrects_draft_and_failure_retains_sources():
    case, spec = spec_fixture()
    e = source("Restaurant listed in a historical dining guide.")
    correction = source("Restaurant closed in 2021.", "https://example.org/closure")
    class Search:
        provider = "tavily_search"
        async def search_sources(self, *args, review=False):
            return ([correction] if review else [e]), 1
    class Local:
        async def generate(self, schema, system, data, ctx):
            if schema is SearchTasks:
                return SearchTasks(queries=["restaurant reviews"])
            if "draft" in json.loads(data):
                return ResearchDraft(findings=[finding(correction, assessment="conflicting",
                    explanation="The current closure report contradicts the historical listing.")])
            return ResearchDraft(findings=[finding(e)], check_query="restaurant closure")
    search = Search()
    result = await ResearchAgent(Local(), search).research(case, spec, RunContext())
    research = result.research[0]
    assert research.review_completed
    assert research.findings[0].citations[0].evidence_id == correction.id
    assert research.search_calls == 3
    class FailingSearch(Search):
        async def search_sources(self, *args, review=False):
            if review:
                raise httpx.ConnectError("SECRET")
            return [e], 1
    failed = await ResearchAgent(Local(), FailingSearch()).research(case, spec, RunContext())
    assert failed.research[0].findings[0].citations[0].evidence_id == e.id
    assert failed.coverage[0].status == "truncated"
    assert "SECRET" not in failed.model_dump_json()


async def test_call_budget_and_synthesis_failure_keep_returned_evidence():
    case, spec = spec_fixture()
    e = source()
    class Search:
        provider = "tavily_search"
        async def search_sources(self, *args, **kwargs):
            return [e], 1
    class Local:
        async def generate(self, schema, *args):
            if schema is SearchTasks:
                return SearchTasks(queries=["transit"])
            raise ValueError("Bad model response")
    result = await ResearchAgent(Local(), Search()).research(case, spec, RunContext())
    assert result.evidence and not result.research[0].findings
    assert result.coverage[0].status == "truncated"
    async with httpx.AsyncClient() as http:
        from surreal_estate.orchestrator.context import BudgetExceeded
        with pytest.raises(BudgetExceeded):
            await TavilyClient(http, "SECRET").search_sources("query", spec,
                RunContext(budget=Budget(max_web_search_calls=0)))


def test_new_research_survives_snapshot_export_and_projection(tmp_path):
    e = source()
    research = WebResearch(topic="neighborhood_discussion", findings=[finding(e)],
        evidence_ids=[e.id], queries=["Pittsburgh transit"], search_calls=1, usage_credits=1)
    report = RunReport(case=fixture_case(), result=ChannelResult(evidence=[e], research=[research],
        coverage=[Coverage(channel="web", provider="tavily_search", topic=research.topic,
            status="complete", reason="Findings retained")]))
    outcome = RunOutcome(report, [])
    path = save_development_snapshot(outcome, path=str(tmp_path / "report.json"))
    restored = load_snapshot_outcome(str(path))
    assert restored.report.result.research == [research]
    exported = build_export(report, PolicyGate())
    assert exported.report.result.research == [research]
    assert exported.report.result.evidence == [e]
    assert exported.omissions.web_topics == []
    bench = bench_response(build_frontend_response(restored))
    assert bench["research"][0]["findings"][0]["ui_id"].startswith("web-")
    assert bench["findings"][0]["research_topic"] == research.topic
    assert bench["findings"][0]["section"] == "Web research"


def test_missing_citation_source_cannot_enter_report():
    from pydantic import ValidationError
    e = source()
    with pytest.raises(ValidationError):
        ChannelResult(research=[WebResearch(topic="neighborhood_discussion",
            findings=[finding(e)], evidence_ids=[e.id])])


def test_numbered_passages_attach_original_text_and_constrain_model_refs():
    from pydantic import ValidationError

    from surreal_estate.channels.web.research import (
        LocalBrief,
        LocalFinding,
        brief_schema,
        convert_brief,
    )
    e = source("First exact sentence.\nSecond exact sentence.")
    brief = LocalBrief(findings=[LocalFinding(title="Transit", statement="A reported theme",
        kind="opinion", source_refs=["S1:P2"])])
    converted = convert_brief(brief, [e])
    assert converted.findings[0].citations[0].excerpt == "Second exact sentence."
    assert converted.findings[0].citations[0].evidence_id == e.id
    with pytest.raises(ValidationError):
        brief_schema([e]).model_validate({"findings": [{"title": "Transit", "statement": "Theme",
            "kind": "opinion", "source_refs": ["S1:P1-8"]}]})


def test_invented_numeric_address_is_rejected():
    from surreal_estate.channels.web.research import validate_findings
    e = source("The diner serves breakfast at 310 Grant Street.")
    f = finding(e).model_copy(update={"statement": "The diner is at 414 Grant Street."})
    assert validate_findings(ResearchDraft(findings=[f]), [e]) == []


def test_serialized_planner_query_is_normalized_before_search():
    from surreal_estate.channels.web.research import search_text
    assert search_text('{"geography":"Pittsburgh","title":"Pittsburgh Reddit living"}') == "Pittsburgh Reddit living"
    assert search_text('{"geography":"Pittsburgh"}') is None
    assert search_text('{malformed') is None


def test_thread_question_preview_is_not_a_neighborhood_opinion():
    from surreal_estate.channels.web.research import validate_findings
    e = source("Would you recommend living there?", "https://reddit.com/r/example/thread")
    f = finding(e).model_copy(update={"statement": "The city is recommended by discussion participants."})
    assert validate_findings(ResearchDraft(findings=[f]), [e], "neighborhood_discussion") == []


def test_location_details_are_reported_facts_even_if_model_labels_opinion():
    from surreal_estate.channels.web.research import validate_findings
    e = source("The restaurant is at 310 Grant Street.")
    f = finding(e).model_copy(update={"title": "Restaurant location", "statement": e.excerpt})
    checked = validate_findings(ResearchDraft(findings=[f]), [e], "restaurant_reviews")
    assert checked[0].kind == "reported_fact"


def test_demographic_and_duplicate_findings_are_omitted():
    from surreal_estate.channels.web.research import validate_findings
    e = source("The street has older residents. The bus is convenient.")
    demographic = finding(e).model_copy(update={"title": "Resident demographics"})
    useful = finding(e).model_copy(update={"statement": "The bus is convenient."})
    checked = validate_findings(ResearchDraft(findings=[demographic, useful, useful]), [e])
    assert len(checked) == 1
