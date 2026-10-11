from surreal_estate.models import ChannelResult, Coverage, PropertyCase
from surreal_estate.orchestrator.context import RunContext


class ListingChannel:
    name = "listing"

    async def run(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        return ChannelResult(
            coverage=[
                Coverage(
                    channel=self.name,
                    topic="documents",
                    status="not_implemented",
                    reason="PDF/page extraction and photo questions are not implemented; upload flow is pending",
                )
            ]
        )
