"""Bounded, cached and attributed OpenStreetMap context."""

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from surreal_estate.channels.apis.common import add_record, coverage, distance_m, public_json
from surreal_estate.orchestrator.context import BudgetExceeded

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRROR = "https://overpass.private.coffee/api/interpreter"

# One independent result cap per category prevents dense transit data from
# crowding schools or groceries out of the same request.
AMENITY_CATEGORIES = {
    "schools": ("Schools", ('["amenity"="school"]',)),
    "groceries": (
        "Grocery stores",
        ('["shop"~"^(supermarket|convenience|greengrocer|grocery)$"]',),
    ),
    "transit": (
        "Public transit",
        (
            '["highway"="bus_stop"]',
            '["public_transport"="platform"]',
            '["railway"~"^(station|halt|tram_stop)$"]',
        ),
    ),
    "pharmacies": ("Pharmacies", ('["amenity"="pharmacy"]',)),
}
CATEGORY_LIMIT = 50


def amenity_categories(tags):
    categories = []
    if tags.get("amenity") == "school":
        categories.append("schools")
    if tags.get("shop") in {"supermarket", "convenience", "greengrocer", "grocery"}:
        categories.append("groceries")
    if (
        tags.get("highway") == "bus_stop"
        or tags.get("public_transport") == "platform"
        or tags.get("railway") in {"station", "halt", "tram_stop"}
    ):
        categories.append("transit")
    if tags.get("amenity") == "pharmacy":
        categories.append("pharmacies")
    return categories


class OpenStreetMap:
    provider = "openstreetmap"
    topic = "mapped_amenities"

    def __init__(self, http):
        self.http = http

    async def fetch(self, case, ctx, location):
        ctx.policy.require(self.provider, extraction=True)
        if not location:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "An unambiguous geocoded point is required for nearby mapped amenities.",
            )
        around = f"(around:1000,{location.latitude},{location.longitude})"
        query = "[out:json][timeout:10][maxsize:16777216];"
        for category, (_, selectors) in AMENITY_CATEGORIES.items():
            query += "(" + "".join(f"nwr{around}{selector};" for selector in selectors) + ")"
            query += f"->.{category};.{category} out body center {CATEGORY_LIMIT + 1};"
        # Form-encoded QL follows the documented Overpass HTTP interface.
        cache_key = ("overpass", query)
        cached = ctx.public_cache.get(cache_key)
        cache_path = (Path(ctx.public_cache_dir) / (hashlib.sha256(query.encode()).hexdigest() + ".json")
                      if ctx.public_cache_dir else None)
        if not cached and cache_path:
            try:
                if cache_path.stat().st_size <= 2_000_000:
                    stored = json.loads(cache_path.read_text())
                    age = (datetime.now(UTC) - datetime.fromisoformat(stored["retrieved_at"])).total_seconds()
                    valid = (isinstance(stored.get("data"), dict)
                             and isinstance(stored["data"].get("elements"), list)
                             and not stored["data"].get("remark"))
                    if valid and 0 <= age < 7 * 86400 and stored["endpoint"] in {OVERPASS_ENDPOINT, OVERPASS_MIRROR}:
                        cached = (time.monotonic() - age, stored["data"], stored["endpoint"], stored["retrieved_at"])
            except (OSError, ValueError, KeyError, TypeError):
                pass  # Cache availability never determines whether live research can run.
        stale = cached if cached and 0 <= time.monotonic() - cached[0] < 7 * 86400 else None
        stale_used = False
        endpoint = OVERPASS_ENDPOINT
        cached_at = None
        if cached and 0 <= time.monotonic() - cached[0] < 86400:
            _, data, endpoint, cached_at = cached
        else:
            for endpoint in (OVERPASS_ENDPOINT, OVERPASS_MIRROR):
                try:
                    data, _ = await public_json(
                        self.http, ctx, self.provider, endpoint, data={"data": query},
                        request_seconds=(8.0 if stale else 35.0) if endpoint == OVERPASS_ENDPOINT else 12.0,
                        retries=1 if endpoint == OVERPASS_ENDPOINT else 0,
                    )
                    if data.get("remark") or not isinstance(data.get("elements"), list):
                        raise ValueError("Overpass returned an incomplete query result")
                    break
                except (httpx.HTTPError, TimeoutError, ValueError, BudgetExceeded) as exc:
                    if endpoint == OVERPASS_MIRROR or isinstance(exc, BudgetExceeded):
                        if stale:
                            _, data, endpoint, cached_at = stale
                            stale_used = True
                            break
                        raise
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {406, 429}:
                        # The public operator requests a pause after rate/admission rejection.
                        if ctx.remaining < 36:
                            raise
                        await asyncio.sleep(30)
                    ctx.trace.append("source:openstreetmap:trying_mirror")
        elements = data["elements"]
        if not isinstance(elements, list):
            raise TypeError("Overpass elements must be a list")
        groups = {key: {} for key in AMENITY_CATEGORIES}
        for element in elements:
            kind, identifier = element["type"], element["id"]
            if (
                kind not in {"node", "way", "relation"}
                or type(identifier) is not int
                or identifier <= 0
            ):
                raise ValueError("Invalid OSM object identifier")
            tags = element.get("tags", {})
            categories = amenity_categories(tags)
            if not categories:
                continue
            center = element if kind == "node" else element.get("center", {})
            distance = None
            if "lat" in center and "lon" in center:
                distance = distance_m(
                    location.latitude,
                    location.longitude,
                    float(center["lat"]),
                    float(center["lon"]),
                )
            member = {
                "object_type": kind,
                "object_id": identifier,
                "uri": f"https://www.openstreetmap.org/{kind}/{identifier}",
                "name": str(tags.get("name") or "Unnamed mapped feature")[:180],
                "tags": tags,
                "center": {key: center[key] for key in ("lat", "lon") if key in center},
                "approximate_center_distance_m": round(distance) if distance is not None else None,
            }
            for category in categories:
                # A stop tagged under multiple conventions is still one OSM object.
                groups[category][(kind, identifier)] = member
        any_features = any(groups.values())
        result = coverage(
            self.provider,
            self.topic,
            "complete" if any_features else "empty",
            "Four area summaries: schools, groceries, public transit and pharmacies. "
            "One 1 km Overpass query; at most 50 supporting objects per category. "
            "Counts describe mapped features, not a verified count of distinct facilities. "
            "Missing data does not imply absence; distances are straight-line to points/centers.",
        )
        notes = {
            "schools": "Attendance zones and school quality are not established.",
            "groceries": "Includes supermarkets, convenience stores and produce shops; hours are not verified.",
            "transit": "Stop/platform features may share a station; frequency and routes are not verified.",
            "pharmacies": "Opening hours and dispensing services are not verified.",
        }
        for category, (title, _) in AMENITY_CATEGORIES.items():
            members = list(groups[category].values())
            limited = len(members) > CATEGORY_LIMIT
            members.sort(
                key=lambda item: (
                    item["approximate_center_distance_m"] is None,
                    item["approximate_center_distance_m"] or 0,
                    item["object_type"],
                    item["object_id"],
                )
            )
            members = members[:CATEGORY_LIMIT]
            nearest = members[0]["approximate_center_distance_m"] if members else None
            if members:
                count = f"at least {len(members)}" if limited else str(len(members))
                statement = f"{title}: {count} mapped features in the 1 km search area. "
                if nearest is not None:
                    statement += f"Closest returned point/center is about {nearest} m away in a straight line. "
                statement += notes[category]
            else:
                statement = f"{title}: no mapped features returned in the 1 km search area. This does not establish that none exist."
            add_record(
                result,
                provider=self.provider,
                topic=self.topic,
                uri=f"https://www.openstreetmap.org/#map=16/{location.latitude}/{location.longitude}",
                title=f"{title} · area summary",
                statement=statement,
                scope=f"1 km search around {location.address}",
                record_id=f"amenities:{category}",
                updated=data.get("osm3s", {}).get("timestamp_osm_base"),
                attribution="© OpenStreetMap contributors · Open Database License (ODbL) · https://www.openstreetmap.org/copyright",
                match_method="overpass_category_summary_1000m_geometry_query",
                details={
                    "query_endpoint": endpoint,
                    "cached_response_retrieved_at": cached_at,
                    "cache_stale": stale_used,
                    "category": category,
                    "query_radius_m": 1000,
                    "mapped_feature_count": len(members),
                    "count_is_lower_bound": limited,
                    "nearest_returned_center_distance_m": nearest,
                    "members": members,
                    "query": query,
                    "license_url": "https://www.openstreetmap.org/copyright",
                },
                flags=[
                    "community_mapped",
                    "address_range_interpolation",
                    "straight_line_not_travel_distance",
                    "mapped_features_not_distinct_facilities",
                ]
                + (["category_results_capped"] if limited else []),
                official=False,
            )
        if not cached_at:
            if len(ctx.public_cache) >= 128:
                ctx.public_cache.pop(next(iter(ctx.public_cache)), None)
            retrieved_at = datetime.now(UTC).isoformat()
            ctx.public_cache[cache_key] = (time.monotonic(), data, endpoint, retrieved_at)
            if cache_path:
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = cache_path.with_suffix(f".{uuid4().hex}.tmp")
                    temporary.write_text(json.dumps({"data": data, "endpoint": endpoint, "retrieved_at": retrieved_at}))
                    temporary.replace(cache_path)
                except OSError:
                    ctx.trace.append("source:openstreetmap:cache_write_unavailable")
        else:
            for evidence in result.evidence:
                evidence.retrieved_at = datetime.fromisoformat(cached_at)
            result.coverage[0].reason += f" Using saved map response retrieved at {cached_at}."
        if stale_used:
            result.coverage[0].status = "truncated"
            result.coverage[0].reason += " Live map refresh failed; showing saved map data, not a fresh lookup."
        return result
