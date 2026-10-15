"""Loopback web app with background research and restart-safe local reports."""

import asyncio
import hashlib
import json
import secrets
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import Field

from surreal_estate.errors import ConfigurationError
from surreal_estate.models import Model, PropertyCase
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.synthesis.frontend import (
    build_frontend_response,
    load_snapshot_outcome,
    save_development_snapshot,
)
from surreal_estate.synthesis.viewer import render_html
from surreal_estate.webapp.display import bench_response


def capabilities():
    """Read-only configuration/readiness check; no generation or paid calls."""
    from dotenv import load_dotenv

    from surreal_estate.llm.brief import GeminiBriefWriter
    from surreal_estate.llm.nemotron import NemotronClient
    from surreal_estate.llm.tavily import TavilyClient

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    available = False
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            TavilyClient(client)
            GeminiBriefWriter(client)
            planner = NemotronClient(client)
            response = client.get(planner.base_url + "/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            available = any(
                m.get("name") in {planner.model, planner.model + ":latest"} for m in models
            )
    except (ConfigurationError, httpx.HTTPError, ValueError, TypeError, KeyError):
        pass
    return {"apis": {"available": True}, "web": {"available": available}}


class AddressRequest(Model):
    address: str = Field(min_length=5, max_length=200)
    geography: str = Field(default="Pittsburgh, Pennsylvania", min_length=3, max_length=120)


async def resolve_address(request):
    from surreal_estate.channels.apis.census import CensusGeocoder

    case = PropertyCase(address=request.address.strip(), geography=request.geography.strip())
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as http:
        return await CensusGeocoder(http).lookup(case, RunContext())


class ResearchRequest(Model):
    address: str = Field(min_length=5, max_length=200)
    geography: str = Field(default="Pittsburgh, Pennsylvania", min_length=3, max_length=120)
    channels: list[Literal["apis", "web"]] = Field(min_length=1, max_length=2)
    topics: list[Literal["neighborhood_discussion", "restaurant_reviews"]] = Field(
        default_factory=list, max_length=2
    )
    demo: bool = False
    confirmation: str | None = Field(default=None, max_length=100)
    parcel_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,40}$")
    request_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,100}$")

    def validate_scope(self):
        self.address = self.address.strip()
        self.geography = self.geography.strip()
        PropertyCase(address=self.address, geography=self.geography)
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("Duplicate channels")
        if "web" in self.channels and not self.topics:
            raise ValueError("Select at least one web research topic")


async def research(request, ctx):
    from surreal_estate.cli import execute

    return await execute(
        SimpleNamespace(
            command="demo" if request.demo else "research",
            address=request.address,
            parcel_id=request.parcel_id,
            geography=request.geography,
            web="web" in request.channels,
            topic=request.topics if "web" in request.channels else [],
            channels=request.channels,
            db=None,
            save_json=False,
        ),
        ctx=ctx,
    )


class App:
    def __init__(self, directory, executor=research, resolver=resolve_address):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.executor = executor
        self.resolver = resolver
        self.matches = {}
        self.csrf = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.jobs = {}
        self.deleted_reports = set()
        self.contexts = {}
        for path in self.directory.glob("job-*.json"):
            try:
                job = json.loads(path.read_text())
                if path.name != f"job-{job['id']}.json" or not self.valid_id(job["id"]):
                    continue
                if job["status"] == "deleted":
                    self.deleted_reports.update([job["id"], job.get("source_report_id")])
                    continue
                if job["status"] == "running":
                    job.update(
                        status="failed",
                        message="The app stopped before this run finished. Start a new research run.",
                    )
                    self.save_job(job)
                self.jobs[job["id"]] = job
            except (ValueError, KeyError, TypeError, OSError):
                continue
        self.import_snapshots()

    def import_snapshots(self):
        """Add a shelf entry for old snapshots; never modify the source file."""
        paths = list(self.directory.glob("*.json"))
        if self.directory.resolve() == Path("exports/web-app").resolve():
            paths += list(self.directory.parent.glob("*.json"))
        known = set()
        for identifier in self.jobs:
            try:
                known.add(
                    load_snapshot_outcome(
                        str(self.directory / f"report-{identifier}.json")
                    ).report.id
                )
            except (OSError, ValueError):
                pass
        for path in paths:
            if path.name.startswith("job-"):
                continue
            try:
                outcome = load_snapshot_outcome(str(path))
                report = outcome.report
                if report.id in known or report.id in self.deleted_reports or not self.valid_id(report.id) or report.id in self.jobs:
                    continue
                identifier = report.id
                target = self.directory / f"report-{identifier}.json"
                if not target.exists():
                    temporary = target.with_suffix(".tmp")
                    save_development_snapshot(outcome, path=str(temporary))
                    temporary.replace(target)
                job = {
                    "id": identifier,
                    "address": report.case.address,
                    "geography": report.case.geography,
                    "channels": report.plan.channels if report.plan else [],
                    "topics": report.case.priorities,
                    "created_at": report.case.as_of.isoformat(),
                    "status": "complete",
                    "demo": report.demo,
                    "partial": any(
                        c.status in {"error", "blocked", "truncated", "not_implemented"}
                        and c.reason != "Not selected for this run"
                        for c in report.result.coverage
                    ),
                    "message": "Saved report",
                    "imported": True,
                }
                self.save_job(job)
                self.jobs[identifier] = job
                known.add(report.id)
            except (ValueError, OSError):
                continue

    @staticmethod
    def valid_id(value):
        from uuid import UUID

        try:
            return str(UUID(value)) == value
        except (ValueError, AttributeError, TypeError):
            return False

    def save_job(self, job):
        target = self.directory / f"job-{job['id']}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(job), encoding="utf-8")
        temporary.replace(target)

    def delete(self, identifier):
        """Delete a finished report; retain a tombstone to prevent automatic reimport."""
        with self.lock:
            if not self.valid_id(identifier) or identifier not in self.jobs:
                raise KeyError(identifier)
            if self.jobs[identifier]["status"] == "running" or identifier in self.contexts:
                raise RuntimeError("Research is still running. Wait until it finishes before deleting it.")
            target = self.directory / f"report-{identifier}.json"
            source_report_id = identifier
            if target.exists():
                source_report_id = load_snapshot_outcome(str(target)).report.id
            self.save_job({"id": identifier, "status": "deleted", "source_report_id": source_report_id})
            try:
                target.unlink(missing_ok=True)
            except OSError:
                self.save_job(self.jobs[identifier])
                raise
            self.deleted_reports.update([identifier, source_report_id])
            del self.jobs[identifier]

    def geocode(self, request):
        from surreal_estate.channels.apis.census import CensusGeocoder

        request.address = request.address.strip()
        request.geography = request.geography.strip()
        case = PropertyCase(address=request.address, geography=request.geography)
        matches, uri = asyncio.run(self.resolver(request))
        candidates = []
        pending = {}
        for match in matches[:20]:
            # Validate every candidate before offering it for confirmation.
            CensusGeocoder(None).from_match(case, match, uri)
            token = secrets.token_urlsafe(32)
            pending[token] = (
                time.monotonic() + 1800,
                request.address,
                request.geography,
                match,
                uri,
            )
            candidates.append(
                {
                    "confirmation": token,
                    "address": match["matchedAddress"],
                    "latitude": float(match["coordinates"]["y"]),
                    "longitude": float(match["coordinates"]["x"]),
                }
            )
        with self.lock:
            self.matches = {
                key: value for key, value in self.matches.items() if value[0] > time.monotonic()
            }
            # Bound the local confirmation cache, including repeated address checks.
            while len(self.matches) + len(pending) > 200:
                self.matches.pop(next(iter(self.matches)))
            self.matches.update(pending)
        return {"candidates": candidates}

    def start(self, request):
        request.validate_scope()
        fingerprint = hashlib.sha256(
            request.model_dump_json(exclude={"confirmation", "request_id"}).encode()
        ).hexdigest()
        with self.lock:
            if request.request_id:
                existing = next(
                    (j for j in self.jobs.values() if j.get("request_id") == request.request_id),
                    None,
                )
                if existing:
                    if existing.get("request_fingerprint") != fingerprint:
                        raise RuntimeError(
                            "This request was already used. Start a new research request."
                        )
                    return self.get(existing["id"])
            if any(job["status"] == "running" for job in self.jobs.values()):
                raise RuntimeError(
                    "A research run is already in progress. Open it below or wait for it to finish."
                )
            confirmed = None
            if not request.demo:
                selected = self.matches.get(request.confirmation)
                if (
                    not selected
                    or selected[0] <= time.monotonic()
                    or selected[1:3] != (request.address, request.geography)
                ):
                    raise RuntimeError(
                        "Check the address and confirm a current match before starting research."
                    )
                confirmed = (selected[3], selected[4])
                request.address = selected[3]["matchedAddress"]
                parts = selected[3].get("addressComponents", {})
                request.geography = (
                    ", ".join(filter(None, [parts.get("city"), parts.get("state")]))
                    or request.geography
                )
            identifier = str(uuid4())
            job = {
                "id": identifier,
                "address": "414 Grant Street (synthetic demo)" if request.demo else request.address,
                "geography": request.geography,
                "channels": request.channels,
                "topics": request.topics,
                "parcel_id": request.parcel_id,
                "demo": request.demo,
                "request_id": request.request_id,
                "request_fingerprint": fingerprint,
                "location": {
                    "latitude": float(confirmed[0]["coordinates"]["y"]),
                    "longitude": float(confirmed[0]["coordinates"]["x"]),
                }
                if confirmed
                else None,
                "created_at": datetime.now(UTC).isoformat(),
                "status": "running",
                "message": "Starting research…",
            }
            self.save_job(job)
            self.jobs[identifier] = job
            self.contexts[identifier] = RunContext(confirmed_geocode=confirmed)
            threading.Thread(target=self.work, args=(identifier, request), daemon=True).start()
            return dict(job)

    def work(self, identifier, request):
        try:
            outcome = asyncio.run(self.executor(request, self.contexts[identifier]))
            with self.lock:
                self.jobs[identifier]["stage"] = "report"
            target = self.directory / f"report-{identifier}.json"
            temporary = target.with_suffix(".tmp")
            save_development_snapshot(outcome, path=str(temporary))
            temporary.replace(target)
            coverage = outcome.report.result.coverage
            partial = any(
                c.status in {"error", "truncated", "blocked", "not_implemented"}
                and c.reason != "Not selected for this run"
                for c in coverage
            )
            update = {
                "status": "complete",
                "partial": partial,
                "message": "Report ready — some research has gaps."
                if partial
                else "Your report is ready.",
            }
        except ConfigurationError:
            update = {
                "status": "failed",
                "message": "Web research is unavailable. Try again, or choose public records only.",
            }
        except Exception:  # noqa: BLE001 — worker boundary must not leak provider exceptions
            # Provider errors can contain secrets, addresses, and raw responses.
            update = {
                "status": "failed",
                "message": "Research could not finish or save its report. Please try again.",
            }
        with self.lock:
            self.jobs[identifier]["elapsed_seconds"] = round(
                time.monotonic() - self.contexts[identifier].started
            )
            self.jobs[identifier].update(update)
            self.jobs[identifier]["progress"] = self.progress(
                self.jobs[identifier], self.contexts[identifier]
            )
            self.contexts.pop(identifier, None)
            try:
                self.save_job(self.jobs[identifier])
            except OSError:
                self.jobs[identifier].update(
                    status="failed",
                    message="Could not save this run. Check available disk space and directory permissions.",
                )

    @staticmethod
    def progress(job, ctx=None):
        """Expose execution milestones, never a fabricated percentage or ETA."""
        trace = list(ctx.trace) if ctx else []
        phases = []
        if "apis" in job.get("channels", []):
            phases.append(
                (
                    "apis",
                    "Public records & nearby places",
                    "channel:apis:started",
                    "channel:apis:finished",
                )
            )
        if "web" in job.get("channels", []):
            phases.append(("plan", "Prepare web research", "planner:started", "planner:validated"))
            phases.append(
                ("web", "Read web sources", "channel:web:started", "channel:web:finished")
            )
        phases.append(("report", "Save your report", "report:started", "report:finished"))
        steps = []
        previous = {s["id"]: s["state"] for s in job.get("progress", {}).get("steps", [])}
        for identifier, title, started, finished in phases:
            state = previous.get(identifier, "waiting")
            if started in trace:
                state = "active"
            if finished in trace:
                state = "done"
            if f"channel:{identifier}:stopped" in trace:
                state = "stopped"
            if identifier == "report" and job.get("stage") == "report":
                state = "active"
            if job["status"] == "complete":
                state = (
                    "done"
                    if identifier == "report" or state == "done"
                    else "stopped"
                    if state in {"active", "stopped"}
                    else "skipped"
                )
            elif job["status"] == "failed" and state == "active":
                state = "stopped"
            elif job["status"] == "failed" and state == "waiting":
                state = "skipped"
            steps.append({"id": identifier, "label": title, "state": state})
        # A later phase means earlier phases have ended, even with coverage gaps.
        active = next(
            (i for i, s in reversed(list(enumerate(steps))) if s["state"] == "active"), None
        )
        if active is not None:
            for step in steps[:active]:
                if step["state"] != "stopped":
                    step["state"] = "skipped" if step["state"] == "waiting" else "done"
        topics = {
            "geocoding": "Checking the address",
            "property_assessment": "Checking property records",
            "building_permits": "Reading building permits",
            "flood_hazard": "Checking flood maps",
            "flood_map_panels": "Reading flood map details",
            "mapped_amenities": "Finding nearby places",
            "street_closures": "Checking street closures",
        }
        source_events = [event.split(":") for event in trace if event.startswith("source:")]
        detail = next(
            (
                topics.get(event[2], "Checking public sources")
                for event in reversed(source_events)
                if len(event) == 4
            ),
            None,
        )
        if any(s["state"] == "active" and s["id"] == "web" for s in steps):
            web_events = [event.split(":") for event in trace if event.startswith("web:")]
            phase = web_events[-1][-1] if web_events else "searching"
            detail = {"planning": "Planning source searches locally", "searching": "Searching web sources",
                      "reading": "Organizing source-linked findings", "checking": "Checking factual uncertainties",
                      "synthesizing": "Writing the final research brief",
                      "finished": "Saving web research"}.get(phase, "Reading web sources")
        if job.get("stage") == "report":
            detail = "Organizing findings and saving sources"
        return {
            "steps": steps,
            "detail": detail,
            "sources_checked": sum(len(e) == 4 and e[3] == "finished" for e in source_events)
            if ctx
            else job.get("progress", {}).get("sources_checked", 0),
        }

    def get(self, identifier):
        with self.lock:
            job = dict(self.jobs[identifier])
            ctx = self.contexts.get(identifier)
            job["progress"] = self.progress(job, ctx)
            if ctx:
                job["elapsed_seconds"] = round(time.monotonic() - ctx.started)
            if ctx and ctx.trace:
                event = ctx.trace[-1].split(":")
                if event[0] == "source":
                    job["message"] = "Researching public records and nearby places…"
                elif event[:2] == ["channel", "web"] or event[:2] in (
                    ["call", "grounded"],
                    ["call", "factcheck"],
                ):
                    job["message"] = "Reading web sources and checking claims…"
                elif event[0] == "planner":
                    job["message"] = "Preparing the research plan…"
            return job

    def outcome(self, identifier):
        if not self.valid_id(identifier) or self.get(identifier)["status"] != "complete":
            raise KeyError(identifier)
        return load_snapshot_outcome(str(self.directory / f"report-{identifier}.json"))


def app_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def allowed_host(self):
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }

        def respond(self, status, body=b"", kind="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self'; img-src https: data:; frame-src 'self' about:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed_host():
                self.respond(403, {"error": "Invalid host"})
                return
            path = urlsplit(self.path).path
            if path in {"/", "/app.js", "/app.css"}:
                filename, kind = {
                    "/": ("index.html", "text/html"),
                    "/app.js": ("app.js", "text/javascript"),
                    "/app.css": ("app.css", "text/css"),
                }[path]
                self.respond(
                    200,
                    files("surreal_estate.webapp").joinpath("static", filename).read_bytes(),
                    kind + "; charset=utf-8",
                )
            elif path == "/api/capabilities":
                self.respond(200, capabilities())
            elif path == "/api/runs":
                with app.lock:
                    jobs = [app.get(key) for key in reversed(app.jobs)]
                self.respond(
                    200,
                    {
                        "runs": sorted(jobs, key=lambda j: j["created_at"], reverse=True),
                        "csrf": app.csrf,
                    },
                )
            elif path.startswith("/api/runs/"):
                try:
                    self.respond(200, app.get(path.removeprefix("/api/runs/")))
                except KeyError:
                    self.respond(404, {"error": "Run not found"})
            elif path.startswith("/reports/"):
                segments = path.strip("/").split("/")
                if len(segments) != 3:
                    self.respond(404, {"error": "Report not found"})
                    return
                _, identifier, page = segments
                try:
                    outcome = app.outcome(identifier)
                    payload = build_frontend_response(outcome)
                    if page == "dashboard":
                        self.respond(
                            200,
                            files("surreal_estate.webapp")
                            .joinpath("static", "index.html")
                            .read_bytes(),
                            "text/html; charset=utf-8",
                        )
                    elif page == "bench.json":
                        self.respond(200, bench_response(payload))
                    elif page == "result.json":
                        self.respond(200, payload.model_dump_json(indent=2))
                    elif page == "source.json":
                        self.respond(
                            200, (app.directory / f"report-{identifier}.json").read_bytes()
                        )
                    elif page == "debug":
                        self.respond(
                            200,
                            render_html(outcome).replace("__DASHBOARD_URL__", "dashboard"),
                            "text/html; charset=utf-8",
                        )
                    else:
                        self.respond(404, {"error": "Report not found"})
                except (KeyError, OSError, ValueError):
                    self.respond(404, {"error": "Saved report unavailable"})
            else:
                self.respond(404, {"error": "Page not found"})

        def do_DELETE(self):
            if not self.allowed_host() or self.headers.get("X-CSRF-Token") != app.csrf:
                self.respond(403, {"error": "Refresh the page and try again."})
                return
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.respond(403, {"error": "Cross-origin request rejected"})
                return
            path = urlsplit(self.path).path
            if not path.startswith("/api/runs/"):
                self.respond(404, {"error": "Report not found"})
                return
            try:
                app.delete(path.removeprefix("/api/runs/"))
            except KeyError:
                self.respond(404, {"error": "Report not found"})
            except RuntimeError as exc:
                self.respond(409, {"error": str(exc)})
            except (OSError, ValueError):
                self.respond(500, {"error": "Cannot delete the report. Check the report directory permissions."})
            else:
                self.respond(200, {"deleted": True})

        def do_POST(self):
            if not self.allowed_host() or self.headers.get("X-CSRF-Token") != app.csrf:
                self.respond(403, {"error": "Refresh the page and try again."})
                return
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.respond(403, {"error": "Cross-origin request rejected"})
                return
            if self.path not in {"/api/runs", "/api/geocode"}:
                self.respond(404, {"error": "Page not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid request size")
                body = self.rfile.read(length)
                if self.path == "/api/geocode":
                    address_request = AddressRequest.model_validate_json(body)
                    PropertyCase(
                        address=address_request.address.strip(),
                        geography=address_request.geography.strip(),
                    )
                    try:
                        result = app.geocode(address_request)
                    except Exception:  # noqa: BLE001 — provider boundary returns a safe error
                        self.respond(
                            502,
                            {"error": "Address lookup is unavailable. Please try again shortly."},
                        )
                        return
                    self.respond(200, result)
                    return
                request = ResearchRequest.model_validate_json(body)
                job = app.start(request)
            except (ValueError, TypeError):
                self.respond(
                    400,
                    {
                        "error": "Enter a full address, geography, and at least one channel. Web research also needs a topic."
                    },
                )
            except RuntimeError as exc:
                self.respond(409, {"error": str(exc)})
            except OSError:
                self.respond(
                    500, {"error": "Cannot save a run. Check the report directory permissions."}
                )
            else:
                self.respond(202, job)

        def log_message(self, *args):
            pass

    return Handler


def serve_app(port=8765, directory="exports/web-app"):
    app = App(directory)
    with ThreadingHTTPServer(("127.0.0.1", port), app_handler(app)) as server:
        server.daemon_threads = True
        print(f"SurrealEstate: http://127.0.0.1:{server.server_port}", flush=True)
        print(
            f"Reports saved locally in {app.directory.resolve()}. Ctrl-C stops the app.", flush=True
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
