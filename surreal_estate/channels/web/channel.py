from dataclasses import dataclass

import httpx

from surreal_estate.channels.web.verifier import verify
from surreal_estate.errors import failure_reason
from surreal_estate.models import (
    ChannelResult,
    Coverage,
    GroundedResponse,
    PropertyCase,
    ResearchQuerySpec,
)
from surreal_estate.orchestrator.context import BudgetExceeded, RunContext


@dataclass
class LiveDisplay:
    """Transient display payload. Deliberately absent from RunReport/store schemas."""

    response: GroundedResponse
    topic: str = "research"
    stage: str = "Search result"


class WebChannel:
    name = "web"

    def __init__(self, queries: list[ResearchQuerySpec], search, extractor=None, fact_checker=None):
        self.queries = queries
        self.search = search
        self.extractor = extractor
        self.fact_checker = fact_checker
        self.displays: list[LiveDisplay] = []

    async def run(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        observations, evidence, coverage = [], [], []
        for spec in self.queries:
            ctx.policy.query(spec, case)
            try:
                response = await self.search.search(spec, ctx)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError, BudgetExceeded) as exc:
                coverage.append(Coverage(
                    channel=self.name, topic=spec.topic,
                    status="truncated" if isinstance(exc, (TimeoutError, BudgetExceeded)) else "error",
                    reason=f"Search stopped ({failure_reason(exc)}); other returned research remains available",
                ))
                continue
            if not response.text or not response.chunks or not response.supports:
                coverage.append(
                    Coverage(
                        channel=self.name,
                        topic=spec.topic,
                        status="truncated" if response.truncated else "empty",
                        reason="Search response truncated before usable support was returned"
                        if response.truncated
                        else "No accessible supported sources returned",
                        queries_run=1,
                    )
                )
                continue
            if response.provider == "gemini_search":
                if not response.search_entry_point:
                    coverage.append(
                        Coverage(
                            channel=self.name,
                            topic=spec.topic,
                            status="blocked",
                            reason="Required Search Suggestions missing",
                            queries_run=1,
                        )
                    )
                    continue
                self.displays.append(LiveDisplay(response, topic=spec.topic))
                coverage.append(
                    Coverage(
                        channel=self.name,
                        topic=spec.topic,
                        status="truncated" if response.truncated else "complete",
                        reason="Search completed · displayed separately"
                        if not response.truncated
                        else "Search response truncated · displayed separately",
                        queries_run=1,
                    )
                )
                if self.fact_checker is not None:
                    coverage.append(await self._recheck(case, spec, response, ctx))
                continue
            if self.extractor is None:
                raise ValueError("Extractable fixture provider requires an extractor")
            extraction = await self.extractor.extract(spec, response, ctx)
            result = verify(spec, response, extraction, ctx.policy)
            observations.extend(result.observations)
            evidence.extend(result.evidence)
            coverage.extend(result.coverage)
        if not self.queries:
            coverage.append(
                Coverage(
                    channel=self.name,
                    topic="research",
                    status="empty",
                    reason="Planner proposed no supported queries",
                )
            )
        return ChannelResult(observations=observations, evidence=evidence, coverage=coverage)

    async def _recheck(self, case, spec, original, ctx) -> Coverage:
        before = ctx.counts.get("factcheck", 0)
        try:
            checked = await self.fact_checker.recheck(case, spec, original, ctx)
            count = ctx.counts.get("factcheck", 0) - before
            if not checked.text or not checked.chunks or not checked.supports:
                return Coverage(
                    channel="fact_checker",
                    topic=spec.topic,
                    status="truncated" if checked.truncated else "empty",
                    reason="Re-check truncated before usable support was returned; original search remains available"
                    if checked.truncated
                    else "Re-check returned no supported evidence; original search remains available",
                    queries_run=count,
                )
            if not checked.search_entry_point:
                return Coverage(
                    channel="fact_checker",
                    topic=spec.topic,
                    status="blocked",
                    reason="Re-check display missing required Search Suggestions",
                    queries_run=count,
                )
            self.displays.append(
                LiveDisplay(checked, topic=spec.topic, stage="Claim re-check · model assessment")
            )
            return Coverage(
                channel="fact_checker",
                topic=spec.topic,
                status="truncated" if checked.truncated else "complete",
                reason="Claim re-check displayed · model assessment, not independent verification",
                queries_run=count,
            )
        except (
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
            TimeoutError,
            BudgetExceeded,
        ) as exc:
            return Coverage(
                channel="fact_checker",
                topic=spec.topic,
                status="truncated" if isinstance(exc, (TimeoutError, BudgetExceeded)) else "error",
                reason=f"Re-check stopped ({failure_reason(exc)}); original search remains available",
                queries_run=ctx.counts.get("factcheck", 0) - before,
            )
