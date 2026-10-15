"""Bounded live Tavily/Nemotron smoke; never print credentials or provider bodies."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from dotenv import load_dotenv

from surreal_estate.channels.web.research import ResearchAgent
from surreal_estate.llm.brief import GeminiBriefWriter
from surreal_estate.llm.nemotron import NemotronClient
from surreal_estate.llm.tavily import TavilyClient
from surreal_estate.models import PropertyCase, ResearchQuerySpec, RunReport
from surreal_estate.orchestrator.context import Budget, RunContext
from surreal_estate.orchestrator.runner import RunOutcome
from surreal_estate.synthesis.frontend import save_development_snapshot


async def main():
    args = argparse.ArgumentParser()
    args.add_argument("--topic", choices=["restaurant_reviews", "neighborhood_discussion"],
                      default="restaurant_reviews")
    args.add_argument("--output", default="/tmp/surreal-tavily-smoke/report.json")
    args.add_argument("--replay", help="Reprocess a saved Tavily source snapshot without new searches")
    options = args.parse_args()
    load_dotenv(Path.cwd() / ".env", override=False)
    case = PropertyCase(address="414 Grant Street, Pittsburgh, PA 15219", geography="Pittsburgh, PA",
                        priorities=[options.topic])
    from datetime import timedelta
    spec = ResearchQuerySpec(topic=options.topic, geography=case.geography, address_anchor=case.address,
        start_date=case.as_of - timedelta(days=365), end_date=case.as_of,
        source_types=["reviews" if options.topic == "restaurant_reviews" else "discussion"])
    ctx = RunContext(budget=Budget(deadline_seconds=180, max_web_search_calls=3))
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        search = TavilyClient(http)
        if options.replay:
            from surreal_estate.channels.web.research import (
                brief_schema,
                convert_brief,
                payload,
                prompt_for,
                validate_findings,
            )
            from surreal_estate.synthesis.frontend import load_snapshot_outcome
            saved = load_snapshot_outcome(options.replay)
            sources = saved.report.result.evidence
            model = NemotronClient(http)
            brief = await model.generate(brief_schema(sources), prompt_for(spec), payload(spec, sources), ctx)
            print(json.dumps({"model_refs": [{"kind": f.kind, "source_refs": f.source_refs} for f in brief.findings]}))
            converted = convert_brief(brief, sources)
            checked = validate_findings(converted, sources, spec.topic)
            print(json.dumps({"supported_findings": len(checked)}))
            original = saved.report.result.research[0]
            research = original.model_copy(update={"findings": checked,
                "limitations": list(dict.fromkeys(original.limitations + converted.limitations))[:12],
                "follow_up_questions": converted.follow_up_questions})
            coverage = [c.model_copy(update={"reason": f"{len(checked)} source-linked findings from {len(sources)} sources. "
                + ("Targeted AI review completed; not independent verification." if research.review_completed
                   else "No targeted factual review completed.")}) if c.topic == research.topic else c
                for c in saved.report.result.coverage]
            if not checked:
                research.limitations.append("No supported topic findings could be produced from the returned passages.")
                coverage = [c.model_copy(update={"status": "truncated"}) if c.topic == research.topic else c
                            for c in coverage]
            result = saved.report.result.model_copy(update={"research": [research], "coverage": coverage})
            report = saved.report.model_copy(update={"result": result})
            save_development_snapshot(RunOutcome(report, []), path=options.output)
            return 0 if checked else 1
        result = await ResearchAgent(NemotronClient(http), search, GeminiBriefWriter(http)).research(case, spec, ctx)
    report = RunReport(case=case, result=result)
    path = save_development_snapshot(RunOutcome(report, []), path=options.output)
    print(json.dumps({"snapshot": str(path), "sources": len(result.evidence),
        "findings": len(result.research[0].findings), "review_completed": result.research[0].review_completed,
        "coverage": result.coverage[0].status, "limitations": result.research[0].limitations,
        "calls": ctx.counts, "steps": [{"stage": e.stage, "status": e.status,
        "seconds": round(e.duration_seconds, 1)} for e in ctx.debug.events]}, indent=2))
    return 0 if result.research[0].findings else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
