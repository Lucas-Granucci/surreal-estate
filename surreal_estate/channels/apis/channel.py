"""Default key-free structured research; one provider failure cannot erase others."""

import httpx

from surreal_estate.channels.apis.census import CensusGeocoder
from surreal_estate.channels.apis.common import coverage, merge
from surreal_estate.channels.apis.spatial import FEMA, OpenStreetMap
from surreal_estate.channels.apis.wprdc import Assessments, Closures, Permits
from surreal_estate.errors import failure_reason
from surreal_estate.models import ChannelResult, ResearchPlan
from surreal_estate.orchestrator.context import BudgetExceeded
from surreal_estate.policy.gate import PolicyDenied


class DataPlanner:
    """Structured-only runs need neither a local model nor a paid API."""

    async def plan(self, case, ctx):
        return ResearchPlan(channels=["apis"], queries=[])


class StructuredDataChannel:
    name = "apis"
    default_enabled = True

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.partial_result = ChannelResult()

    async def run(self, case, ctx):
        results = []
        self.partial_result = ChannelResult()

        async def attempt(adapter, *args):
            before = ctx.counts.get("api", 0)
            topic = getattr(adapter, "topic", "geocoding")
            ctx.trace.append(f"source:{adapter.provider}:{topic}:started")
            try:
                result = await adapter.fetch(case, ctx, *args)
            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                TypeError,
                TimeoutError,
                BudgetExceeded,
                OverflowError,
            ) as exc:
                status = (
                    "blocked"
                    if isinstance(exc, PolicyDenied)
                    else "truncated"
                    if isinstance(exc, (TimeoutError, BudgetExceeded))
                    else "error"
                )
                result = coverage(
                    adapter.provider,
                    topic,
                    status,
                    f"Source lookup stopped ({failure_reason(exc, provider=adapter.provider)}); other sources remain available.",
                )
            if result.coverage:
                result.coverage[0].queries_run = ctx.counts.get("api", 0) - before
                result.coverage[0].sources_returned = len(result.evidence)
            results.append(result)
            self.partial_result = merge(results)
            ctx.trace.append(f"source:{adapter.provider}:{topic}:finished")
            return result

        census = CensusGeocoder(self.http)
        census_result = await attempt(census)
        location = census.location if census_result.evidence else None
        assessment = Assessments(self.http)
        assessment_result = await attempt(assessment, location)
        parcel = assessment.parcel if assessment_result.evidence else None
        await attempt(Permits(self.http), location, parcel, assessment.resolution)
        await attempt(FEMA(self.http), location)
        await attempt(FEMA(self.http, panels=True), location)
        await attempt(OpenStreetMap(self.http), location)
        await attempt(Closures(self.http), location)
        return self.partial_result
