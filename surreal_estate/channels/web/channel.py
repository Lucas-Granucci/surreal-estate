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

    def __init__(self, queries: list[ResearchQuerySpec], search, extractor=None):
        self.queries = queries
        self.search = search
        self.extractor = extractor
        self.displays: list[LiveDisplay] = []

    async def run(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        observations, evidence, coverage, research = [], [], [], []
        for spec in self.queries:
            ctx.policy.query(spec, case)
            if getattr(self.search, "provider", None) == "tavily_search":
                result = await self.extractor.research(case, spec, ctx)
                observations.extend(result.observations)
                evidence.extend(result.evidence)
                coverage.extend(result.coverage)
                research.extend(result.research)
                continue
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
            if response.provider != "synthetic_web":
                raise ValueError("Only Tavily is supported for live web research")
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
        return ChannelResult(observations=observations, evidence=evidence, coverage=coverage,
                             research=research)
