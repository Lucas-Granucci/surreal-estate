"""Current WPRDC resources, resolved by catalog name rather than pinned UUIDs."""

import json
import math
import re
from datetime import date, timedelta
from uuid import UUID

from surreal_estate.channels.apis.common import add_record, coverage, public_json
from surreal_estate.channels.apis.parcel_resolution import resolve_parcel
from surreal_estate.models import ParcelCandidate

API = "https://data.wprdc.org/api/3/action/"
ASSESSMENT_FIELDS = (
    "PARID,PROPERTYHOUSENUM,PROPERTYFRACTION,PROPERTYADDRESS,PROPERTYCITY,PROPERTYSTATE,"
    "PROPERTYUNIT,PROPERTYZIP,MUNICODE,MUNIDESC,CLASSDESC,USEDESC,LOTAREA,"
    "RECORDDATE,SALEDATE,SALEPRICE,SALECODE,SALEDESC,COUNTYBUILDING,COUNTYLAND,COUNTYTOTAL,"
    "FAIRMARKETTOTAL,STYLEDESC,STORIES,YEARBLT,TOTALROOMS,BEDROOMS,FULLBATHS,HALFBATHS,"
    "FINISHEDLIVINGAREA,CARDNUMBER,TAXYEAR,ASOFDATE"
)
PERMIT_FIELDS = (
    "permit_id,permit_type,work_description,work_type,commercial_or_residential,"
    "total_project_value,issue_date,parcel_num,address,latitude,longitude,zip_code,status"
)
CLOSURE_FIELDS = (
    "closure_id,permit_id,permit_type,work_description,work_type,from_date,to_date,active,"
    "primary_street,from_street,to_street,full_closure,travel_lane,parking_lane,sidewalk,"
    "segment_num,total_segments,roadway_id,geometry"
)


class WPRDC:
    def __init__(self, http, ctx, provider, dataset, resource_name):
        self.http, self.ctx, self.provider = http, ctx, provider
        self.dataset, self.resource_name = dataset, resource_name
        self.resource = None
        self.metadata = None

    async def resolve(self):
        data, _ = await public_json(
            self.http, self.ctx, self.provider, API + "package_show", params={"id": self.dataset}
        )
        if data.get("success") is not True:
            raise ValueError("WPRDC catalog lookup failed")
        self.metadata = data["result"]
        if self.metadata.get("license_id") not in {"cc-zero", "cc-by"}:
            raise ValueError("WPRDC dataset license changed; review needed")
        choices = [
            r
            for r in self.metadata["resources"]
            if r.get("datastore_active") is True and r.get("name") == self.resource_name
        ]
        if len(choices) != 1:
            raise ValueError("Current WPRDC DataStore resource unavailable or ambiguous")
        self.resource = choices[0]
        UUID(self.resource["id"])
        return self

    @property
    def uri(self):
        return f"https://data.wprdc.org/dataset/{self.dataset}/resource/{self.resource['id']}"

    @property
    def updated(self):
        return self.resource.get("last_modified")

    @property
    def attribution(self):
        publisher = (
            "Allegheny County" if self.dataset == "property-assessments" else "City of Pittsburgh"
        )
        return f"{publisher} / Western Pennsylvania Regional Data Center · {self.metadata['license_id']}"

    async def rows(self, filters, fields, limit, sort):
        data, _ = await public_json(
            self.http,
            self.ctx,
            self.provider,
            API + "datastore_search",
            params={
                "resource_id": self.resource["id"],
                "filters": json.dumps(filters),
                "fields": fields,
                "limit": limit,
                "sort": sort,
            },
        )
        if data.get("success") is not True:
            raise ValueError("WPRDC DataStore query failed")
        result = data["result"]
        if not set(fields.split(",")) <= {f["id"] for f in result["fields"]}:
            raise ValueError("WPRDC schema changed; requested fields missing")
        # Retain only explicitly requested property fields even if an upstream
        # schema change causes the server to include extra personal columns.
        records = [{key: row.get(key) for key in fields.split(",")} for row in result["records"]]
        return records, int(result["total"])

    def details(self, record):
        return {
            "dataset": self.dataset,
            "resource_id": self.resource["id"],
            "catalog_updated_at": self.metadata.get("metadata_modified"),
            "record": record,
        }


def street(location):
    c = location.components
    return " ".join(
        str(c.get(key) or "").strip()
        for key in (
            "preQualifier",
            "preDirection",
            "preType",
            "streetName",
            "suffixType",
            "suffixDirection",
            "suffixQualifier",
        )
        if c.get(key)
    ).upper()


def clean(value):
    return re.sub(r"\s+", " ", str(value or "").upper().strip())


def parcel_key(value):
    return re.sub(r"[^A-Z0-9]", "", clean(value))


class Assessments:
    provider = "wprdc_assessments"
    topic = "property_assessment"

    def __init__(self, http):
        self.http = http
        self.parcel = None
        self.resolution = None

    async def fetch(self, case, ctx, location):
        self.parcel = None
        self.resolution = None
        if not location or not location.allegheny:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "An unambiguous Census location in Allegheny County is required.",
            )
        number = re.match(r"^(\d+)\s+", location.address)
        requested = re.match(r"^(\d+)\s+", case.address)
        if (
            not number
            or not requested
            or number[1] != requested[1]
            or re.search(r"\b(APT|UNIT|SUITE|STE)\b|#|\d/\d|^\d+-", case.address, re.I)
        ):
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "Unit, fractional, ranged, or changed house-number matches require manual parcel selection.",
            )
        road = street(location)
        zipcode = location.components.get("zip", "")[:5]
        if not road or not zipcode:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "Census street and ZIP are required for an exact assessment match.",
            )
        client = await WPRDC(
            self.http,
            ctx,
            self.provider,
            "property-assessments",
            "Property Assessments Parcel Data (API version)",
        ).resolve()
        filters = {
            "PROPERTYHOUSENUM": number[1],
            "PROPERTYADDRESS": road,
            "PROPERTYZIP": zipcode,
            "PROPERTYSTATE": "PA",
        }
        rows, total = await client.rows(filters, ASSESSMENT_FIELDS, 21, '"PARID" asc')
        limited = total > 21 or len(rows) > 21
        # Verify response fields as well as the server filter. Never pick the first parcel.
        rows = [
            r
            for r in rows
            if all(clean(r.get(k)) == clean(v) for k, v in filters.items())
            and not clean(r.get("PROPERTYUNIT"))
            and not clean(r.get("PROPERTYFRACTION"))
        ]
        if any(not r.get("PARID") for r in rows):
            raise ValueError("Assessment record missing parcel ID")
        parcels = {str(r["PARID"]) for r in rows}
        if (case.parcel_id and case.parcel_id not in parcels) or (
            not case.parcel_id and not parcels
        ):
            reason = (
                "The selected parcel does not match this address's county candidates. Review the candidates and select again."
                if case.parcel_id
                else "No matching county parcel returned. This does not establish that the property is absent from county records."
            )
            result = coverage(
                self.provider,
                self.topic,
                "blocked" if parcels or case.parcel_id else "empty",
                reason,
            )
            distinct = {str(row["PARID"]): row for row in rows}
            result.coverage[0].parcel_candidates = [
                ParcelCandidate(
                    parcel_id=identifier,
                    address=f"{row['PROPERTYHOUSENUM']} {row['PROPERTYADDRESS']}, {row.get('PROPERTYCITY') or ''} PA {zipcode}",
                    property_use=str(
                        row.get("USEDESC") or row.get("CLASSDESC") or "Use not supplied"
                    ),
                    assessed_value=str(row["COUNTYTOTAL"])
                    if row.get("COUNTYTOTAL") is not None
                    else None,
                    lot_area=str(row["LOTAREA"]) if row.get("LOTAREA") is not None else None,
                    source_url=client.uri,
                )
                for identifier, row in distinct.items()
            ]
            return result
        if case.parcel_id:
            self.parcel = case.parcel_id
        elif len({parcel_key(p) for p in parcels}) > 1 or limited:
            self.parcel, self.resolution = await resolve_parcel(
                self.http,
                ctx,
                rows,
                number[1],
                road,
                zipcode,
                limited=limited,
            )
        else:
            self.parcel = sorted(parcels)[0]
        rows = [row for row in rows if parcel_key(row["PARID"]) == parcel_key(self.parcel)]
        result = coverage(
            self.provider,
            self.topic,
            "complete",
            "User-selected parcel validated against exact address candidates; this is not parcel-boundary verification."
            if case.parcel_id
            else "Unique exact house number/street/ZIP match; address matching is not a parcel-boundary verification.",
        )
        if self.resolution:
            result.coverage[0].reason = (
                f"Automatically selected parcel {self.parcel}. " + self.resolution["reason"]
            )
        for row in rows:
            values = []
            for key, title in [
                ("YEARBLT", "recorded year built"),
                ("FINISHEDLIVINGAREA", "living area (sq ft)"),
                ("BEDROOMS", "bedrooms"),
                ("FULLBATHS", "full baths"),
                ("COUNTYTOTAL", "county assessment (USD)"),
            ]:
                if row.get(key) is not None:
                    values.append(f"{title}: {row[key]}")
            statement = (
                f"County parcel {self.parcel}: "
                + ("; ".join(values) or "address record returned")
                + ". Assessment records are not current appraisals or proof of condition."
            )
            if self.resolution:
                statement = (
                    f"Automatically selected parcel {self.parcel}"
                    + (
                        " (uncertain match). "
                        if self.resolution["uncertain"]
                        else " (county GIS supported). "
                    )
                    + statement
                )
            add_record(
                result,
                provider=self.provider,
                topic=self.topic,
                uri=client.uri,
                title=f"Allegheny County assessment · {self.parcel}",
                statement=statement,
                scope=location.address,
                details={
                    **client.details(row),
                    **({"parcel_resolution": self.resolution} if self.resolution else {}),
                },
                record_id=self.parcel,
                updated=client.updated,
                record_date=row.get("ASOFDATE"),
                attribution=client.attribution,
                match_method=self.resolution["method"]
                if self.resolution
                else "user_selected_exact_address_candidate"
                if case.parcel_id
                else "unique_exact_number_street_zip_no_unit",
                flags=[
                    *(
                        ["parcel_selection_uncertain"]
                        if self.resolution and self.resolution["uncertain"]
                        else []
                    ),
                    "assessment_not_appraisal",
                    "current_snapshot_not_historical",
                ],
            )
        return result


class Permits:
    provider = "wprdc_permits"
    topic = "building_permits"

    def __init__(self, http):
        self.http = http

    async def fetch(self, case, ctx, location, parcel, resolution=None):
        if not location or not location.pittsburgh:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "City of Pittsburgh jurisdiction not confirmed by Census; PLI does not cover other municipalities.",
            )
        if not parcel:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "No county parcel could be selected for this address.",
            )
        client = await WPRDC(self.http, ctx, self.provider, "pli-permits", "PLI Permits").resolve()
        rows, total = await client.rows(
            {"parcel_num": parcel}, PERMIT_FIELDS, 51, '"issue_date" desc'
        )
        rows = [r for r in rows if parcel_key(r.get("parcel_num")) == parcel_key(parcel)]
        limited = total > 50 or len(rows) > 50
        result = coverage(
            self.provider,
            self.topic,
            "truncated" if limited else "complete" if rows else "empty",
            "Up to 50 most recently issued permits on the matched parcel, including Building & Development Applications. Feed starts June 2019; plumbing excluded. No records is not proof of no work or no permits.",
        )
        if resolution:
            result.coverage[0].reason = (
                f"Permits for automatically selected parcel {parcel}"
                + (" (uncertain match). " if resolution["uncertain"] else ". ")
                + result.coverage[0].reason
            )
        for row in rows[:50]:
            if not row.get("permit_id"):
                raise ValueError("Permit record missing identifier")
            description = str(row.get("work_description") or "No work description")[:160]
            statement = f"PLI {row.get('permit_id')}: {row.get('permit_type')}; issued {row.get('issue_date') or 'date unavailable'}; status {row.get('status') or 'unavailable'}. {description}. A permit does not prove work was completed."
            if resolution and resolution["uncertain"]:
                statement = f"Uncertain parcel match: automatically selected {parcel}. " + statement
            add_record(
                result,
                provider=self.provider,
                topic=self.topic,
                uri=client.uri,
                title=f"Pittsburgh PLI permit · {row.get('permit_id')}",
                statement=statement,
                scope=location.address,
                details={
                    **client.details(row),
                    **({"parcel_resolution": resolution} if resolution else {}),
                },
                record_id=row.get("permit_id"),
                updated=client.updated,
                record_date=row.get("issue_date"),
                attribution=client.attribution,
                match_method="exact_county_parcel_id",
                flags=[
                    *(
                        ["parcel_selection_uncertain"]
                        if resolution and resolution["uncertain"]
                        else []
                    ),
                    "permit_not_completion",
                    "plumbing_excluded",
                    "current_snapshot_not_historical",
                ],
            )
        return result


def segment_distance(location, points):
    """Local planar point-to-polyline distance; feed pairs are [latitude, longitude]."""
    scale = math.cos(math.radians(location.latitude))
    xy = []
    for lat, lon in points:
        lat, lon = float(lat), float(lon)
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not (-90 <= lat <= 90 and -180 <= lon <= 180)
        ):
            raise ValueError("Invalid closure geometry")
        xy.append(((lon - location.longitude) * 111320 * scale, (lat - location.latitude) * 111320))
    distances = [math.hypot(x, y) for x, y in xy]
    for (ax, ay), (bx, by) in zip(xy, xy[1:]):
        dx, dy = bx - ax, by - ay
        t = max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) if dx or dy else 0
        distances.append(math.hypot(ax + t * dx, ay + t * dy))
    return min(distances) if distances else float("inf")


class Closures:
    provider = "wprdc_closures"
    topic = "street_closures"

    def __init__(self, http):
        self.http = http

    async def fetch(self, case, ctx, location):
        if not location or not location.pittsburgh:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "City of Pittsburgh jurisdiction not confirmed by Census; DOMI is city-only.",
            )
        road = street(location)
        if not road:
            return coverage(
                self.provider,
                self.topic,
                "blocked",
                "No normalized street available for a bounded closure lookup.",
            )
        client = await WPRDC(
            self.http, ctx, self.provider, "street-closures", "Street Closures"
        ).resolve()
        rows, total = await client.rows(
            {"primary_street": road}, CLOSURE_FIELDS, 201, '"from_date" desc'
        )
        result = coverage(
            self.provider, self.topic, "empty", "No matching closure records returned."
        )
        skipped = 0
        for row in rows[:200]:
            if clean(row.get("primary_street")) != road:
                continue
            try:
                end = date.fromisoformat(row["to_date"][:10]) if row.get("to_date") else None
                start = date.fromisoformat(row["from_date"][:10]) if row.get("from_date") else None
                if end and end < case.as_of or start and start > case.as_of + timedelta(days=90):
                    continue
                points = (
                    json.loads(row["geometry"])
                    if isinstance(row.get("geometry"), str)
                    else row["geometry"]
                )
                distance = segment_distance(location, points)
            except (ValueError, TypeError, KeyError):
                skipped += 1
                continue
            if distance > 1000:
                continue
            description = " ".join(str(row.get("work_description") or "").split())
            work = f" Work described: {description[:180]}." if description else ""
            statement = f"DOMI closure {row.get('closure_id')} on {road}, about {distance:.0f} m from the interpolated address point: {row.get('from_date') or 'start unknown'} to {row.get('to_date') or 'end unknown'}.{work} Permit records do not confirm work is underway."
            details = client.details(row)
            details.update({"approximate_segment_distance_m": round(distance), "radius_m": 1000})
            add_record(
                result,
                provider=self.provider,
                topic=self.topic,
                uri=client.uri,
                title=f"DOMI street closure · {row.get('closure_id')} · segment {row.get('segment_num')}",
                statement=statement,
                scope=f"{road}, Pittsburgh",
                details=details,
                record_id=f"{row.get('closure_id')}:{row.get('roadway_id')}",
                updated=client.updated,
                record_date=row.get("from_date"),
                attribution=client.attribution,
                match_method="same_street_and_segment_within_1000m_of_interpolated_point",
                flags=["address_range_interpolation", "permit_not_active_work", "same_street_only"],
            )
        result.coverage[0].status = (
            "truncated" if total > 200 or skipped else "complete" if result.evidence else "empty"
        )
        result.coverage[0].reason = (
            "Same-street segments within 1 km; excludes ended records and starts beyond 90 days. "
            "Missing end dates remain uncertain, not confirmed active. Other streets are not searched. "
            f"Examined at most 200 of {total} street records; {skipped} records lacked usable dates/geometry. "
            "Empty results do not prove no closures."
        )
        return result
