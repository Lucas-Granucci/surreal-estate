"""Generate at most five paid sample runs, serially; reuse completed snapshots."""
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx

from surreal_estate.channels.apis.census import CensusGeocoder
from surreal_estate.cli import execute
from surreal_estate.models import PropertyCase
from surreal_estate.orchestrator.context import RunContext


async def main():
    candidates = json.loads(Path('showcase/candidates.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', action='append', help='Candidate id; repeat to select several')
    args = parser.parse_args()
    directory = Path('exports/showcase')
    directory.mkdir(parents=True, exist_ok=True)
    for item in candidates:
        if args.only and item['id'] not in args.only:
            continue
        path = Path(item.get('snapshot', directory / f"{item['id']}.json"))
        if path.exists():
            print('REUSE', item['id'], str(path), flush=True)
            continue
        print('START', item['id'], item['address'], flush=True)
        try:
            async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as http:
                matches, uri = await CensusGeocoder(http).lookup(
                    PropertyCase(address=item['address'], geography='Pittsburgh, Pennsylvania'),
                    RunContext(),
                )
            if len(matches) != 1:
                print('REJECT_GEOCODE', item['id'], len(matches), flush=True)
                continue
            ctx = RunContext(confirmed_geocode=(matches[0], uri),
                             public_cache_dir='exports/web-app/source-cache')
            outcome = await execute(SimpleNamespace(command='research', address=matches[0]['matchedAddress'],
                geography='Pittsburgh, Pennsylvania', web=True, channels=['apis','web'],
                topic=['neighborhood_discussion','restaurant_reviews'], db=None, export=str(path)), ctx=ctx)
            print('DONE', item['id'], ctx.counts,
                  [(r.topic, r.synthesis_status) for r in outcome.report.result.research],
                  [(c.topic,c.status) for c in outcome.report.result.coverage], flush=True)
        except (httpx.HTTPError, ValueError, RuntimeError, TimeoutError, OSError) as exc:
            print('FAILED', item['id'], type(exc).__name__, flush=True)


if __name__ == '__main__':
    asyncio.run(main())
