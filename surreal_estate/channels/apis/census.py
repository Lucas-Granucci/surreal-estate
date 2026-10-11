import asyncio

import httpx

from surreal_estate.models import ChannelResult, Coverage, Evidence, Observation, PropertyCase
from surreal_estate.orchestrator.context import RunContext


class CensusGeocoder:
    name = "apis"
    provider = "census"

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def fetch(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        ctx.policy.require("census")
        timeout = ctx.reserve("api")
        async with asyncio.timeout(timeout):
            response = await self.http.get(
                "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
                params={
                    "address": case.address,
                    "benchmark": "Public_AR_Current",
                    "format": "json",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            matches = response.json()["result"]["addressMatches"]
        if len(matches) != 1:
            return ChannelResult(
                coverage=[
                    Coverage(
                        channel=self.name,
                        provider=self.provider,
                        topic="geocoding",
                        status="empty" if not matches else "blocked",
                        reason="No address match"
                        if not matches
                        else "Ambiguous address; no match selected",
                    )
                ]
            )
        match = matches[0]
        coordinates = match["coordinates"]
        lat, lon = float(coordinates["y"]), float(coordinates["x"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid Census coordinates")
        statement = (
            f"Census address match: {match['matchedAddress']}; "
            f"latitude {lat:.6f}, longitude {lon:.6f}. "
            "Address-range interpolation, not a parcel or structure assessment."
        )
        evidence = Evidence(
            provider="census",
            uri=str(response.url),
            title="Census Geocoder",
            excerpt=statement,
            retention="persistent",
            kind="official_record",
        )
        return ChannelResult(
            evidence=[evidence],
            observations=[
                Observation(
                    topic="geocoding",
                    statement=statement,
                    evidence_ids=[evidence.id],
                    location_scope=match["matchedAddress"],
                    observed_on=case.as_of,
                    qualifier="official_record",
                    confidence=1,
                    flags=["address_range_interpolation", "match_requires_user_review"],
                )
            ],
            coverage=[
                Coverage(
                    channel=self.name,
                    provider=self.provider,
                    topic="geocoding",
                    status="complete",
                    reason="One Census match returned; not independently confirmed",
                    sources_returned=1,
                )
            ],
        )

    async def run(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        return await self.fetch(case, ctx)
