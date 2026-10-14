import re

import httpx

from surreal_estate.channels.apis.common import Location, public_json
from surreal_estate.models import ChannelResult, Coverage, Evidence, Observation, PropertyCase
from surreal_estate.orchestrator.context import RunContext


# Recognize an explicit US state/ZIP suffix so the geography field never
# overwrites a full address (including one outside the default Pittsburgh area).
STATE_CODES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split()
STATE_NAMES = "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|Puerto Rico|Guam|American Samoa|Northern Mariana Islands|Virgin Islands"


def geocoding_address(case: PropertyCase) -> str:
    """Complete street-only input from the user's geography, preserving explicit locality."""
    address = case.address.strip().rstrip(",").strip()
    if re.search(r"\b\d{5}(?:-\d{4})?$", address):
        return address
    regions = "|".join(STATE_CODES) + "|" + STATE_NAMES
    if re.search(rf"(?:,\s*|\s+)(?:{regions})$", address, re.IGNORECASE):
        return address
    geography = [part.strip() for part in case.geography.split(",") if part.strip()]
    city = geography[0] if geography else ""
    if city and re.search(rf"\b{re.escape(city)}$", address, re.IGNORECASE):
        return ", ".join([address, *geography[1:]])
    # A comma followed by another locality is explicit input. Unit suffixes
    # are still street-only input and need the supplied city and region.
    if "," in address and not re.match(r"(?:apt\b|suite\b|unit\b|floor\b|#)", address.rsplit(",", 1)[1].strip(), re.IGNORECASE):
        return address
    return ", ".join([address, *geography])


class CensusGeocoder:
    name = "apis"
    provider = "census"

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.location: Location | None = None

    async def lookup(self, case: PropertyCase, ctx: RunContext):
        query_address = geocoding_address(case)
        payload, response_url = await public_json(
            self.http,
            ctx,
            self.provider,
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
            params={
                "address": query_address,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            },
        )
        return payload["result"]["addressMatches"], response_url

    async def fetch(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        self.location = None
        query_address = geocoding_address(case)
        if ctx.confirmed_geocode is not None:
            match, response_url = ctx.confirmed_geocode
            return self.from_match(case, match, response_url, confirmed=True)
        matches, response_url = await self.lookup(case, ctx)
        if len(matches) != 1:
            return ChannelResult(
                coverage=[
                    Coverage(
                        channel=self.name,
                        provider=self.provider,
                        topic="geocoding",
                        status="empty" if not matches else "blocked",
                        queries_run=1,
                        reason=f"No Census match for {query_address}. Check the street number, city and state, or add a ZIP code, then run research again."
                        if not matches
                        else "Ambiguous address; no match selected",
                    )
                ]
            )
        return self.from_match(case, matches[0], response_url)

    def from_match(self, case, match, response_url, *, confirmed=False):
        query_address = geocoding_address(case)
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
            match_method="user_confirmed_census_address_range_match" if confirmed else "single_census_address_range_match",
            details={
                "submitted_address": query_address,
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
                    flags=["address_range_interpolation", "user_confirmed_match" if confirmed else "match_requires_user_review"],
                )
            ],
            coverage=[
                Coverage(
                    channel=self.name,
                    provider=self.provider,
                    topic="geocoding",
                    status="complete",
                    reason="Address match selected and confirmed by the user" if confirmed else "One Census match returned; not independently confirmed",
                    sources_returned=1,
                    queries_run=1,
                )
            ],
        )

    async def run(self, case: PropertyCase, ctx: RunContext) -> ChannelResult:
        return await self.fetch(case, ctx)
