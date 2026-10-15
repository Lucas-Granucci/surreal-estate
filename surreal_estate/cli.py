import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from surreal_estate.channels.apis.channel import DataPlanner, StructuredDataChannel
from surreal_estate.channels.web.planner import Planner
from surreal_estate.channels.web.research import ResearchAgent
from surreal_estate.errors import ConfigurationError, failure_reason
from surreal_estate.evals.fixtures import (
    FixtureAPI,
    FixtureExtractor,
    FixturePlanner,
    FixtureSearch,
    fixture_case,
)
from surreal_estate.llm.brief import GeminiBriefWriter
from surreal_estate.llm.diagnostics import inspect_models
from surreal_estate.llm.nemotron import NemotronClient
from surreal_estate.llm.tavily import TavilyClient
from surreal_estate.models import PropertyCase
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.orchestrator.runner import run
from surreal_estate.store.export import write_export
from surreal_estate.store.sqlite import Store
from surreal_estate.synthesis.dossier import render_markdown
from surreal_estate.synthesis.frontend import load_snapshot_outcome, save_development_snapshot
from surreal_estate.synthesis.viewer import serve


async def diagnose_gemini():
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as http:
        client = GeminiBriefWriter(http)
        print(f"Configured Gemini model: {client.model}")
        print("Endpoint: Gemini Developer API / v1beta / generateContent")
        present, models = await inspect_models(client)
        print("Configured model supports generateContent: " + ("yes" if present else "not listed"))
        print("Available generateContent models:")
        for model in models:
            print(f"  {model}")
        print(
            "Listing does not guarantee project generation access, free-tier quota."
        )
        return 0 if present else 1


async def execute(args, *, ctx=None):
    # Explicit path avoids searching parent directories for unrelated credentials.
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    ctx = ctx or RunContext(public_cache_dir="exports/source-cache")
    if args.command == "demo":
        outcome = await run(
            fixture_case(),
            ctx,
            FixturePlanner(),
            FixtureAPI(),
            search=FixtureSearch(),
            extractor=FixtureExtractor(),
            demo=True,
        )
    else:
        case = PropertyCase(
            address=args.address,
            geography=args.geography,
            parcel_id=getattr(args, "parcel_id", None),
            priorities=(getattr(args, "topic", None) if getattr(args, "topic", None) is not None
                        else ["neighborhood_discussion", "restaurant_reviews"]),
        )
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as http:
            search = TavilyClient(http) if args.web else None
            nemotron = NemotronClient(http) if args.web else None
            outcome = await run(
                case,
                ctx,
                Planner(nemotron, web_enabled=True) if args.web else DataPlanner(),
                StructuredDataChannel(http),
                search=search,
                extractor=ResearchAgent(nemotron, search, GeminiBriefWriter(http)) if search else None,
                selected_channels=getattr(args, "channels", None),
            )
    if args.db:
        store = Store(args.db)
        try:
            store.save(outcome.report, ctx.policy)
        finally:
            store.close()
    if getattr(args, "durable_export", None):
        write_export(args.durable_export, outcome.report, ctx.policy)
    if getattr(args, "export", None):
        outcome.snapshot_path = str(save_development_snapshot(outcome, path=args.export))
    elif getattr(args, "save_json", False):
        outcome.snapshot_path = str(save_development_snapshot(outcome))
    return outcome


def main():
    parser = argparse.ArgumentParser(description="Local evidence-first property research")
    commands = parser.add_subparsers(dest="command", required=True)
    app = commands.add_parser("app", help="Start the persistent local research web app")
    app.add_argument("--port", type=int, default=8765)
    app.add_argument("--data-dir", default="exports/web-app", help="Saved local report directory")
    commands.add_parser(
        "gemini-models", help="Check configured model against Google's model list; no generation"
    )
    view = commands.add_parser(
        "view", help="Open a saved development results JSON in the local dashboard"
    )
    view.add_argument("path", help="Path to exports/<run-id>.json")
    view.add_argument("--port", type=int, default=8765)
    view.set_defaults(viewer=True)
    demo = commands.add_parser("demo", help="Offline synthetic Pittsburgh fixture")
    demo.add_argument("--db", help="Optional SQLite path")
    research = commands.add_parser(
        "research", help="Default key-free structured data; optional Tavily/Nemotron web research"
    )
    research.add_argument("--address", required=True)
    research.add_argument("--geography", default="Pittsburgh, Pennsylvania")
    research.add_argument("--parcel-id", help="Explicit parcel choice, validated against address candidates")
    research.add_argument(
        "--topic",
        action="append",
        choices=["neighborhood_discussion", "restaurant_reviews"],
        help="Repeat to select topics; default: neighborhood discussion and nearby restaurant reviews",
    )
    research.add_argument(
        "--web", action="store_true", help="Enable Tavily search with local Nemotron research"
    )
    research.add_argument("--db", help="Optional SQLite path; includes retained Tavily research")
    for command in (demo, research):
        command.add_argument(
            "--no-save-json",
            dest="save_json",
            action="store_false",
            default=True,
            help="Disable default development snapshot in exports/<run-id>.json",
        )
        command.add_argument(
            "--export",
            metavar="PATH",
            help="Save full development JSON, including web results, to this path",
        )
        command.add_argument(
            "--durable-export",
            metavar="PATH",
            help="Write policy-filtered processing JSON including Tavily findings",
        )
        command.add_argument(
            "--viewer",
            action="store_true",
            help="Show results and pipeline in a browser, including failed runs",
        )
        command.add_argument(
            "--port",
            type=int,
            default=8765,
            help="Loopback viewer port for SSH forwarding (default: 8765)",
        )
    args = parser.parse_args()
    if hasattr(args, "port") and not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        if args.command == "app":
            from surreal_estate.webapp.server import serve_app

            serve_app(port=args.port, directory=args.data_dir)
            return
        if args.command == "gemini-models":
            parser.exit(asyncio.run(diagnose_gemini()))
        outcome = (
            load_snapshot_outcome(args.path)
            if args.command == "view"
            else asyncio.run(execute(args))
        )
    except ConfigurationError as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    except (ValueError, OSError) as exc:
        parser.exit(
            2, f"Configuration/run error ({type(exc).__name__}); check environment and inputs.\n"
        )
    except httpx.HTTPError as exc:
        parser.exit(2, f"Gemini diagnostic failed: {failure_reason(exc)}\n")
    if outcome.snapshot_path:
        print(f"Development JSON: {outcome.snapshot_path}", flush=True)
    if args.viewer or outcome.displays:
        try:
            serve(outcome, port=args.port)
        except OSError:
            parser.exit(
                2,
                "Viewer could not bind its port. Choose another --port and matching SSH tunnel.\n",
            )
    else:
        print(render_markdown(outcome.report))
    if any(c.status == "error" for c in outcome.report.result.coverage):
        sys.exit(1)


if __name__ == "__main__":
    main()
