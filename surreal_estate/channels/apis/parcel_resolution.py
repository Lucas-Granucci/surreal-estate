"""Deterministic ranking of exact-address parcels with optional county GIS support."""

import json
import math
import re

import httpx

from surreal_estate.channels.apis.common import public_json
from surreal_estate.orchestrator.context import BudgetExceeded

ADDRESS_LAYER = "https://gisdata.alleghenycounty.us/arcgis/rest/services/EGIS/AC_AddressPointsWithLabels/MapServer/0"
PARCEL_LAYER = (
    "https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0"
)
ADDRESS_FIELDS = "OBJECTID,ADDR_NUM,ST_PREFIX,ST_NAME,ST_TYPE,ST_SUFFIX,ZIP_CODE,MUNICIPALITY,PARCELID,UNIT,ADDR_NUM_PREFIX,ADDR_NUM_SUFFIX,ST_PREMODIFIER,ST_PRETYPE,ST_POSTMODIFIER,STATUS"


def normalize(value):
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def key(value):
    return re.sub(r"[^A-Z0-9]", "", normalize(value))


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


async def query(http, ctx, layer, params):
    data, uri = await public_json(
        http,
        ctx,
        "allegheny_gis",
        layer + "/query",
        params={"f": "json", "resultRecordCount": 100, **params},
        request_seconds=4,
    )
    if data.get("error") or not isinstance(data.get("features"), list):
        raise ValueError("County GIS query unavailable")
    if any(
        not isinstance(f, dict)
        or not isinstance(f.get("attributes"), dict)
        or (f.get("geometry") is not None and not isinstance(f["geometry"], dict))
        for f in data["features"]
    ):
        raise ValueError("County GIS feature schema changed")
    if data.get("exceededTransferLimit"):
        raise ValueError("County GIS candidate results incomplete")
    return data["features"], uri


async def resolve_parcel(http, ctx, rows, number, road, zipcode, *, limited=False):
    # Normalize IDs, but retain the original county ID for downstream permit queries.
    identifiers = {}
    for row in sorted(rows, key=lambda r: str(r["PARID"])):
        identifiers.setdefault(key(row["PARID"]), str(row["PARID"]))
    signals = {k: {"address_link": False, "boundary_match": False} for k in identifiers}
    checks = []
    points = []
    # Reserve the usual seven downstream API requests for permits/FEMA/OSM/closures.
    if ctx.budget.max_api_calls - ctx.counts.get("api", 0) >= 9 and ctx.remaining > 10:
        try:
            features, uri = await query(
                http,
                ctx,
                ADDRESS_LAYER,
                {
                    "where": f"ADDR_NUM = {int(number)} AND ZIP_CODE = {literal(zipcode)}",
                    "outFields": ADDRESS_FIELDS,
                    "returnGeometry": "true",
                    "outSR": 4326,
                },
            )
            for feature in features:
                a = feature.get("attributes") or {}
                point_road = " ".join(
                    normalize(a.get(f))
                    for f in (
                        "ST_PREMODIFIER",
                        "ST_PREFIX",
                        "ST_PRETYPE",
                        "ST_NAME",
                        "ST_TYPE",
                        "ST_SUFFIX",
                        "ST_POSTMODIFIER",
                    )
                    if normalize(a.get(f))
                )
                if (
                    normalize(a.get("ADDR_NUM")) != str(number)
                    or normalize(a.get("ZIP_CODE"))[:5] != zipcode
                    or point_road != normalize(road)
                    or any(
                        normalize(a.get(f)) for f in ("UNIT", "ADDR_NUM_PREFIX", "ADDR_NUM_SUFFIX")
                    )
                    or normalize(a.get("STATUS")) in {"INACTIVE", "RETIRED", "DELETED"}
                ):
                    continue
                # A parcel link is strongest when it belongs to the exact county candidate set.
                linked = key(a.get("PARCELID"))
                if linked in signals:
                    signals[linked]["address_link"] = True
                geometry = feature.get("geometry") or {}
                x, y = geometry.get("x"), geometry.get("y")
                if (
                    isinstance(x, (int, float))
                    and isinstance(y, (int, float))
                    and math.isfinite(x)
                    and math.isfinite(y)
                    and -180 <= x <= 180
                    and -90 <= y <= 90
                ):
                    points.append([x, y])
            checks.append(
                {
                    "source": ADDRESS_LAYER,
                    "query_url": uri,
                    "status": "complete",
                    "matched_points": len(points),
                }
            )
            if points:
                features, uri = await query(
                    http,
                    ctx,
                    PARCEL_LAYER,
                    {
                        "where": "1=1",
                        "outFields": "PIN,MAPBLOCKLOT",
                        "returnGeometry": "false",
                        "geometry": json.dumps(
                            {"points": points, "spatialReference": {"wkid": 4326}}
                        ),
                        "geometryType": "esriGeometryMultipoint",
                        "inSR": 4326,
                        "spatialRel": "esriSpatialRelIntersects",
                    },
                )
                for feature in features:
                    a = feature.get("attributes") or {}
                    for field in ("PIN", "MAPBLOCKLOT"):
                        if key(a.get(field)) in signals:
                            signals[key(a[field])]["boundary_match"] = True
                checks.append({"source": PARCEL_LAYER, "query_url": uri, "status": "complete"})
        except (httpx.HTTPError, ValueError, TypeError, KeyError, TimeoutError, BudgetExceeded):
            checks.append(
                {
                    "status": "unavailable",
                    "reason": "County GIS could not complete; retained address candidates used.",
                }
            )
    else:
        checks.append(
            {"status": "skipped", "reason": "Preserved time and API budget for remaining research."}
        )

    def score(identifier):
        item = signals[identifier]
        return (int(item["address_link"]) + int(item["boundary_match"]), int(item["address_link"]))

    ranked = sorted(identifiers, key=lambda k: (*(-v for v in score(k)), k))
    selected = ranked[0]
    tied = sum(score(k) == score(selected) for k in ranked) > 1
    corroborated = score(selected)[0] > 0
    conflicting = any(k != selected and any(signals[k].values()) for k in ranked)
    uncertain = tied or not corroborated or limited or conflicting
    method = "county_gis_ranked" if corroborated and not tied else "stable_parcel_id_fallback"
    reason = (
        "County address-point parcel link and/or intersecting parcel boundary ranked this candidate first."
        if not tied and corroborated
        else "Candidates could not be distinguished; selected by normalized parcel ID, not response order."
    )
    if conflicting:
        reason += " County GIS also supports another candidate; the selection remains uncertain."
    if limited:
        reason += (
            " Address candidate results were capped; selection is among retained candidates only."
        )
    return identifiers[selected], {
        "selected_parcel_id": identifiers[selected],
        "method": method,
        "uncertain": uncertain,
        "reason": reason,
        "candidate_count": len(ranked),
        "candidates_limited": limited,
        "candidates": [{"parcel_id": identifiers[k], **signals[k]} for k in ranked],
        "checks": checks,
    }
