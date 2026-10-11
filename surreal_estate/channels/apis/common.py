"""Bounded public-data requests and shared provenance helpers."""

import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from surreal_estate.models import ChannelResult, Coverage, Evidence, Observation
from surreal_estate.orchestrator.context import RunContext


@dataclass
class Location:
    latitude: float
    longitude: float
    address: str
    components: dict = field(default_factory=dict)
    geographies: dict = field(default_factory=dict)

    def in_geography(self, layer: str, geoid: str) -> bool:
        rows = self.geographies.get(layer, [])
        return len(rows) == 1 and rows[0].get("GEOID") == geoid

    @property
    def allegheny(self):
        return self.in_geography("Counties", "42003")

    @property
    def pittsburgh(self):
        return self.in_geography("Incorporated Places", "4261000")


async def public_json(
    http,
    ctx: RunContext,
    provider: str,
    url: str,
    *,
    params=None,
    data=None,
    content: str | None = None,
    request_seconds: float = 12.0,
):
    """One budget reservation per dispatch; bounded time and body, no implicit retries."""
    if data is not None and content is not None:
        raise ValueError("Choose form data or raw content, not both")
    if not 0 < request_seconds <= 35:
        raise ValueError("Public-data request timeout must be between 0 and 35 seconds")
    rule = ctx.policy.require(provider, extraction=True)
    if urlsplit(url).hostname not in rule["hosts"] or not url.startswith("https://"):
        raise ValueError("Provider endpoint outside source policy")
    timeout = min(request_seconds, ctx.reserve("api"), max(0.001, ctx.remaining - 0.05))
    async with asyncio.timeout(timeout):
        async with http.stream(
            "POST" if data is not None or content is not None else "GET",
            url,
            params=params,
            data=data,
            content=content,
            headers={
                "User-Agent": "SurrealEstate/0.1 (+https://github.com/Lucas-Granucci/surreal-estate)",
                "Accept": "application/json",
                **({"Content-Type": "text/plain; charset=utf-8"} if content is not None else {}),
            },
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 2_000_000:
                    raise ValueError("Public-data response exceeds size limit")
            payload = json.loads(chunks)
            if not isinstance(payload, dict):
                raise ValueError("Expected a public-data JSON object")
            return payload, str(response.url)


def coverage(provider, topic, status, reason, *, queries=0, sources=0):
    return ChannelResult(
        coverage=[
            Coverage(
                channel="apis",
                provider=provider,
                topic=topic,
                status=status,
                reason=reason,
                queries_run=queries,
                sources_returned=sources,
            )
        ]
    )


def merge(results):
    return ChannelResult(
        observations=[o for r in results for o in r.observations],
        evidence=[e for r in results for e in r.evidence],
        coverage=[c for r in results for c in r.coverage],
    )


def add_record(
    result,
    *,
    provider,
    topic,
    uri,
    title,
    statement,
    scope,
    details,
    record_id=None,
    updated=None,
    record_date=None,
    attribution=None,
    match_method=None,
    flags=(),
    official=True,
):
    evidence = Evidence(
        provider=provider,
        uri=uri,
        title=title,
        excerpt=statement[:1000],
        retention="persistent",
        kind="official_record" if official else "reported",
        record_id=str(record_id) if record_id is not None else None,
        source_updated_at=str(updated) if updated is not None else None,
        record_date=str(record_date) if record_date is not None else None,
        attribution=attribution,
        match_method=match_method,
        details=details,
    )
    result.evidence.append(evidence)
    result.observations.append(
        Observation(
            topic=topic,
            statement=statement[:500],
            evidence_ids=[evidence.id],
            location_scope=scope,
            observed_on=datetime.now(UTC).date(),
            qualifier="official_record" if official else "reported",
            confidence=0.8,
            flags=list(flags),
        )
    )


def distance_m(lat1, lon1, lat2, lon2):
    if not all(math.isfinite(x) for x in (lat1, lon1, lat2, lon2)):
        raise ValueError("Invalid coordinates")
    if not (-90 <= lat2 <= 90 and -180 <= lon2 <= 180):
        raise ValueError("Invalid coordinates")
    a, b = math.radians(lat1), math.radians(lat2)
    h = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))
