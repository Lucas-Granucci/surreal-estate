"""Retry only map evidence for an existing sample; no paid/model calls."""
import argparse
import asyncio
from uuid import uuid4

import httpx

from surreal_estate.channels.apis.common import Location
from surreal_estate.channels.apis.spatial import OpenStreetMap
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.synthesis.frontend import load_snapshot_outcome, save_development_snapshot


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source = args.source
    outcome = load_snapshot_outcome(source)
    evidence = next(e for e in outcome.report.result.evidence if e.provider == 'census')
    d = evidence.details
    location = Location(d['latitude'], d['longitude'], d['matched_address'],
                        d['address_components'], d['geographies'])
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        ctx = RunContext(public_cache_dir='exports/web-app/source-cache')
        result = await OpenStreetMap(http).fetch(outcome.report.case, ctx, location)
    existing = outcome.report.result
    existing.coverage = [c for c in existing.coverage if c.topic != 'mapped_amenities'] + result.coverage
    existing.observations = [o for o in existing.observations if o.topic != 'mapped_amenities'] + result.observations
    existing.evidence = [e for e in existing.evidence if e.provider != 'openstreetmap'] + result.evidence
    outcome.report.id = str(uuid4())
    path = save_development_snapshot(outcome, path=args.output)
    print('MAP_RECOVERED', path, ctx.counts, len(result.evidence))


if __name__ == '__main__':
    asyncio.run(main())
