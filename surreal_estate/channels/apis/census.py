import httpx

from surreal_estate.channels.apis.common import Location, public_json
from surreal_estate.models import ChannelResult, Coverage, Evidence, Observation, PropertyCase
from surreal_estate.orchestrator.context import RunContext


class CensusGeocoder:
    name = "apis"
    provider = "census"

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.location: Location | None = None

    async def fetch(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        self.location = None
        payload, response_url = await public_json(
            self.http,
            ctx,
            self.provider,
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
            params={
                "address": case.address,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            },
        )
        matches = payload["result"]["addressMatches"]
        if len(matches) != 1:
            return ChannelResult(
                coverage=[
                    Coverage(
                        channel=self.name,
                        provider=self.provider,
                        topic="geocoding",
                        status="empty" if not matches else "blocked",
                        queries_run=1,
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
        self.location = Location(
            lat,
            lon,
            match["matchedAddress"],
            match.get("addressComponents", {}),
            match.get("geographies", {}),
        )
        statement = (
            f"Census address match: {match['matchedAddress']}; "
            f"latitude {lat:.6f}, longitude {lon:.6f}. "
            "Address-range interpolation, not a parcel or structure assessment."
        )
        evidence = Evidence(
            provider="census",
            uri=response_url,
            title="Census Geocoder",
            excerpt=statement,
            retention="persistent",
            kind="official_record",
            match_method="single_census_address_range_match",
            details={
                "latitude": lat,
                "longitude": lon,
                "matched_address": match["matchedAddress"],
                "address_components": match.get("addressComponents", {}),
                "geographies": match.get("geographies", {}),
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
            },
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
                    queries_run=1,
                )
            ],
        )

    async def run(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        return await self.fetch(case, ctx)
