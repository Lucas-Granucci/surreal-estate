"""Bounded, key-free live check of default public sources (no LLM or Gemini calls)."""

import argparse
import asyncio

import httpx

from surreal_estate.channels.apis.channel import StructuredDataChannel
from surreal_estate.models import PropertyCase
from surreal_estate.orchestrator.context import RunContext


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="414 Grant Street, Pittsburgh, PA 15219")
    args = parser.parse_args()
    case = PropertyCase(address=args.address, geography="Pittsburgh, Pennsylvania")
    ctx = RunContext()
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as http:
        result = await StructuredDataChannel(http).run(case, ctx)
    for item in result.coverage:
        print(
            f"{item.provider}/{item.topic}: {item.status}; {item.queries_run} calls; {item.sources_returned} records; {item.reason}",
            flush=True,
        )
    print(f"Total API calls: {ctx.counts.get('api', 0)}", flush=True)
    return int(any(c.status == "error" for c in result.coverage))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
