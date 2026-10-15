"""Live integration check. Prints metadata; saves a development snapshot in exports/."""

import asyncio
from argparse import ArgumentParser, Namespace

from surreal_estate.cli import execute


async def main(topics=None):
    topics = topics or ["neighborhood_discussion", "restaurant_reviews"]
    outcome = await execute(
        Namespace(
            command="research",
            address="414 Grant Street, Pittsburgh, PA 15219",
            geography="Pittsburgh, Pennsylvania",
            web=True,
            db=None,
            save_json=True,
            topic=topics,
        )
    )
    print("Development JSON:", outcome.snapshot_path)
    for event in outcome.debug_events:
        print(
            f"{event.stage}: {event.status}, HTTP {event.http_status}, {event.duration_seconds:.2f}s"
        )
        if event.stage in {"Policy gate", "Fact-check policy"} and event.status == "error":
            print("Policy diagnostic:", event.parsed)
            if event.stage == "Policy gate":
                print(
                    "Allowed date/topics:",
                    event.request["case"]["as_of"],
                    event.request["case"]["priorities"],
                )
                print(
                    "Proposed topic/date windows:",
                    [
                        (q["topic"], q["start_date"], q["end_date"])
                        for q in event.request["plan"]["queries"]
                    ],
                )
        if event.error == "ValidationError" and event.parsed:
            print(
                "Validation fields:",
                [(item["loc"], item["type"]) for item in event.parsed["validation_errors"]],
            )
        if event.stage.startswith("Tavily"):
            print("Search metadata:", event.parsed)
            if isinstance(event.response, dict):
                print(
                    "Completion reasons:",
                    [c.get("finishReason") for c in event.response.get("candidates", [])],
                )
    for coverage in outcome.report.result.coverage:
        print(f"{coverage.channel}/{coverage.topic}: {coverage.status} — {coverage.reason}")
    for display in outcome.displays:
        result = display.response
        print(
            f"{display.topic} / {display.stage}: {len(result.search_queries)} searches, {len(result.chunks)} sources, "
            f"{len(result.supports)} supports; suggestions={bool(result.search_entry_point)}"
        )
    coverage = outcome.report.result.coverage
    attempted = {
        item.topic
        for item in coverage
        if item.channel == "web" and item.status in {"complete", "empty"}
    }
    if attempted != set(topics):
        raise SystemExit("A requested topic was blocked, failed, or truncated; see coverage above")
    if any(not research.findings for research in outcome.report.result.research):
        raise SystemExit("No supported findings produced for a requested topic")
    print(
        "Pipeline smoke test passed. Empty coverage is an honest absence of support, not verified evidence."
    )


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--topic", action="append", choices=["neighborhood_discussion", "restaurant_reviews"]
    )
    asyncio.run(main(parser.parse_args().topic))
