from typing import Protocol

from surreal_estate.models import ChannelResult, PropertyCase
from surreal_estate.orchestrator.context import RunContext


class Channel(Protocol):
    name: str

    async def run(self, case: PropertyCase, ctx: RunContext) -> ChannelResult: ...
