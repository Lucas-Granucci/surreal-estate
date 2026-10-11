"""FEMA point intersections and bounded, attributed OpenStreetMap context."""

from datetime import UTC, datetime

from surreal_estate.channels.apis.common import add_record, coverage, distance_m, public_json

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

FEMA_SERVICE = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"


class FEMA:
    provider = "fema_nfhl"

    def __init__(self, http, *, panels=False):
        self.http = http
        self.panels = panels
        self.topic = "flood_map_panels" if panels else "flood_hazard"
        self.layer = 3 if panels else 28

    async def fetch(self, case, ctx, location):
        if not location:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "An unambiguous geocoded point is required for FEMA map context.",
            )
        fields = (
            "OBJECTID,DFIRM_ID,FIRM_PAN,EFF_DATE,SOURCE_CIT"
            if self.panels
            else "OBJECTID,DFIRM_ID,FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,SOURCE_CIT"
        )
        data, uri = await public_json(
            self.http,
            ctx,
            self.provider,
            f"{FEMA_SERVICE}/{self.layer}/query",
            params={
                "f": "json",
                "geometry": f"{location.longitude},{location.latitude}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": fields,
                "returnGeometry": "false",
                "resultRecordCount": 6,
            },
        )
        if data.get("error") or not isinstance(data.get("features"), list):
            raise ValueError("FEMA service returned an error or missing features")
        features = data["features"]
        limited = data.get("exceededTransferLimit", False) or len(features) > 5
        result = coverage(
            self.provider,
            self.topic,
            "truncated" if limited else "complete" if features else "empty",
            "FEMA point intersection at Census interpolated coordinates. An empty result is unavailable mapped context, not a finding of no flood risk. Multiple intersections are retained without selecting a parcel-wide zone.",
        )
        for feature in features[:5]:
            row = feature["attributes"]
            effective = None
            if self.panels:
                if row.get("EFF_DATE") is not None:
                    effective = (
                        datetime.fromtimestamp(float(row["EFF_DATE"]) / 1000, UTC)
                        .date()
                        .isoformat()
                    )
                identifier = row.get("FIRM_PAN") or row.get("OBJECTID")
                text = f"FEMA map panel {identifier}; effective date {effective or 'unavailable'}. The panel intersects the interpolated address point; it is not a parcel-boundary determination."
            else:
                if not row.get("FLD_ZONE"):
                    raise ValueError("FEMA hazard feature missing zone")
                identifier = row.get("FLD_AR_ID") or row.get("OBJECTID")
                text = f"FEMA maps zone {row['FLD_ZONE']} ({row.get('ZONE_SUBTY') or 'subtype unspecified'}) at the interpolated address point; special flood hazard area field: {row.get('SFHA_TF') or 'unspecified'}. Preliminary map context, not a parcel or building flood determination."
            add_record(
                result,
                provider=self.provider,
                topic=self.topic,
                uri=uri,
                title=f"FEMA NFHL · {'panel' if self.panels else 'hazard area'} {identifier}",
                statement=text,
                scope=location.address,
                record_id=identifier,
                record_date=effective,
                details={
                    "service": FEMA_SERVICE,
                    "layer_id": self.layer,
                    "attributes": row,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                },
                attribution="Federal Emergency Management Agency · National Flood Hazard Layer",
                match_method="point_intersection_census_interpolated_coordinates",
                flags=[
                    "address_range_interpolation",
                    "not_parcel_flood_determination",
                    "current_map_not_historical",
                ],
            )
        return result


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
        # Raw QL and project identification are required by the verified endpoint.
        data, _ = await public_json(
            self.http, ctx, self.provider, OVERPASS_ENDPOINT, content=query, request_seconds=35.0
        )
        if data.get("remark"):
            raise ValueError("Overpass returned an incomplete query result")
        elements = data["elements"]
        if not isinstance(elements, list):
            raise ValueError("Overpass elements must be a list")
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
                    "query_endpoint": OVERPASS_ENDPOINT,
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
        return result
