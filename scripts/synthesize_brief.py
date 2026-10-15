"""Write Gemini briefs from saved Tavily evidence, without new searches."""
import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from dotenv import load_dotenv

from surreal_estate.errors import failure_reason
from surreal_estate.llm.brief import GeminiBriefWriter
from surreal_estate.models import ChannelResult, ResearchQuerySpec, identifier
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.synthesis.frontend import load_snapshot_outcome, save_development_snapshot


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", required=True)
    parser.add_argument("--topic", choices=["neighborhood_discussion", "restaurant_reviews"])
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env", override=False)
    outcome = load_snapshot_outcome(args.input)
    outcome.report.id = identifier()
    # Preserve the original report; a newly written brief is a separate saved result.
    ctx = RunContext()
    by_id = {e.id: e for e in outcome.report.result.evidence}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        writer = GeminiBriefWriter(http)
        for research in outcome.report.result.research:
            if args.topic and research.topic != args.topic:
                continue
            sources = [by_id[i] for i in research.evidence_ids]
            if not sources or any(e.provider != "tavily_search" for e in sources):
                raise ValueError("Brief replay requires Tavily source material")
            case = outcome.report.case
            spec = ResearchQuerySpec(topic=research.topic, geography=case.geography,
                address_anchor=case.address, start_date=case.as_of - timedelta(days=365),
                end_date=case.as_of, source_types=["reviews" if research.topic == "restaurant_reviews" else "discussion"])
            research.brief = await writer.write(case, spec, research, sources, ctx)
            research.summary = research.brief.overview.text[:1200]
            research.synthesis_status = "complete"
            research.limitations = [item for item in research.limitations
                                    if not item.startswith("Final brief unavailable:")]
            for coverage in outcome.report.result.coverage:
                if (coverage.topic == research.topic and coverage.provider == "tavily_search"
                        and not coverage.reason.startswith("Source-cited research brief available.")):
                    coverage.reason = "Source-cited research brief available. " + coverage.reason
            print(f"{research.topic}: {len(research.brief.sections)} cited sections; no search tools")
    outcome.report.result = ChannelResult.model_validate(outcome.report.result.model_dump())
    path = save_development_snapshot(outcome, path=args.output)
    print(f"Saved: {path}")
    print(f"Report ID: {outcome.report.id}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.HTTPStatusError as exc:
        from surreal_estate.orchestrator.debug import DebugLog
        try:
            diagnostic = exc.response.json().get("error", {}).get("message", "Provider request rejected")
        except (ValueError, AttributeError):
            diagnostic = "Provider request rejected"
        raise SystemExit("Brief writing failed: " + DebugLog().clean(str(diagnostic))[:1500]) from None
    except ValueError as exc:
        from surreal_estate.orchestrator.debug import DebugLog
        raise SystemExit("Brief writing failed: " + DebugLog().clean(str(exc))[:1500]) from None
    except (httpx.HTTPError, TimeoutError) as exc:
        raise SystemExit("Brief writing failed: " + failure_reason(exc)) from None
