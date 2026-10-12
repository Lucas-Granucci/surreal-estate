"""Loopback web app with background research and restart-safe local reports."""

import asyncio
import json
import secrets
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field

from surreal_estate.errors import ConfigurationError
from surreal_estate.models import Model, PropertyCase
from surreal_estate.orchestrator.context import RunContext
from surreal_estate.synthesis.dashboard import render_dashboard
from surreal_estate.synthesis.frontend import build_frontend_response, load_snapshot_outcome, save_development_snapshot
from surreal_estate.synthesis.viewer import render_html
from typing import Literal


class ResearchRequest(Model):
    address: str = Field(min_length=5, max_length=200)
    geography: str = Field(default="Pittsburgh, Pennsylvania", min_length=3, max_length=120)
    channels: list[Literal["apis", "web"]] = Field(min_length=1, max_length=2)
    topics: list[Literal["neighborhood_discussion", "restaurant_reviews"]] = Field(default_factory=list, max_length=2)
    demo: bool = False
    parcel_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,40}$")

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

    return await execute(SimpleNamespace(
        command="demo" if request.demo else "research", address=request.address,
        parcel_id=request.parcel_id,
        geography=request.geography, web="web" in request.channels,
        topic=request.topics if "web" in request.channels else [],
        channels=request.channels, db=None, save_json=False,
    ), ctx=ctx)


class App:
    def __init__(self, directory, executor=research):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.executor = executor
        self.csrf = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.jobs = {}
        self.contexts = {}
        for path in self.directory.glob("job-*.json"):
            try:
                job = json.loads(path.read_text())
                if path.name != f"job-{job['id']}.json" or not self.valid_id(job['id']):
                    continue
                if job["status"] == "running":
                    job.update(status="failed", message="The app stopped before this run finished. Start a new research run.")
                    self.save_job(job)
                self.jobs[job["id"]] = job
            except (ValueError, KeyError, TypeError, OSError):
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

    def start(self, request):
        request.validate_scope()
        with self.lock:
            if any(job["status"] == "running" for job in self.jobs.values()):
                raise RuntimeError("A research run is already in progress. Open it below or wait for it to finish.")
            identifier = str(uuid4())
            job = dict(id=identifier, address="414 Grant Street (synthetic demo)" if request.demo else request.address,
                       geography=request.geography, channels=request.channels, demo=request.demo,
                       created_at=datetime.now(UTC).isoformat(), status="running", message="Starting research…")
            self.save_job(job)
            self.jobs[identifier] = job
            self.contexts[identifier] = RunContext()
            threading.Thread(target=self.work, args=(identifier, request), daemon=True).start()
            return dict(job)

    def work(self, identifier, request):
        try:
            outcome = asyncio.run(self.executor(request, self.contexts[identifier]))
            target = self.directory / f"report-{identifier}.json"
            temporary = target.with_suffix(".tmp")
            save_development_snapshot(outcome, path=str(temporary))
            temporary.replace(target)
            coverage = outcome.report.result.coverage
            partial = any(c.status in {"error", "truncated", "blocked", "not_implemented"}
                          and c.reason != "Not selected for this run" for c in coverage)
            update = dict(status="complete", partial=partial,
                          message="Report ready — some research has gaps." if partial else "Your report is ready.")
        except ConfigurationError:
            update = dict(status="failed", message="Web research is not configured. Check the Gemini key and local model settings in .env, or run structured data only.")
        except Exception:
            # Provider errors can contain secrets, addresses, and raw responses.
            update = dict(status="failed", message="Research could not finish or save its report. Check the local provider configuration and that the report directory is writable, then try again.")
        with self.lock:
            self.jobs[identifier].update(update)
            self.contexts.pop(identifier, None)
            try:
                self.save_job(self.jobs[identifier])
            except OSError:
                self.jobs[identifier].update(status="failed", message="Could not save this run. Check available disk space and directory permissions.")

    def get(self, identifier):
        with self.lock:
            job = dict(self.jobs[identifier])
            ctx = self.contexts.get(identifier)
            if ctx and ctx.trace:
                event = ctx.trace[-1].split(":")
                if event[0] == "source":
                    job["message"] = "Researching public records and nearby places…"
                elif event[:2] == ["channel", "web"] or event[:2] in (["call", "grounded"], ["call", "factcheck"]):
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
                f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
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
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src https: data:; frame-src 'self' about:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed_host():
                self.respond(403, {"error": "Invalid host"})
                return
            path = urlsplit(self.path).path
            if path in {"/", "/app.js", "/app.css"}:
                filename, kind = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/app.css": ("app.css", "text/css")}[path]
                self.respond(200, files("surreal_estate.webapp").joinpath("static", filename).read_bytes(), kind + "; charset=utf-8")
            elif path == "/api/runs":
                with app.lock:
                    jobs = [app.get(key) for key in reversed(app.jobs)]
                self.respond(200, {"runs": sorted(jobs, key=lambda j: j["created_at"], reverse=True), "csrf": app.csrf})
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
                        self.respond(200, render_dashboard(payload, app_mode=True), "text/html; charset=utf-8")
                    elif page == "result.json":
                        self.respond(200, payload.model_dump_json(indent=2))
                    elif page == "debug":
                        self.respond(200, render_html(outcome).replace("__DASHBOARD_URL__", "dashboard"), "text/html; charset=utf-8")
                    else:
                        self.respond(404, {"error": "Report not found"})
                except (KeyError, OSError, ValueError):
                    self.respond(404, {"error": "Saved report unavailable"})
            else:
                self.respond(404, {"error": "Page not found"})

        def do_POST(self):
            if not self.allowed_host() or self.headers.get("X-CSRF-Token") != app.csrf:
                self.respond(403, {"error": "Refresh the page and try again."})
                return
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.respond(403, {"error": "Cross-origin request rejected"})
                return
            if self.path != "/api/runs":
                self.respond(404, {"error": "Page not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid request size")
                request = ResearchRequest.model_validate_json(self.rfile.read(length))
                job = app.start(request)
            except (ValueError, TypeError):
                self.respond(400, {"error": "Enter a full address, geography, and at least one channel. Web research also needs a topic."})
            except RuntimeError as exc:
                self.respond(409, {"error": str(exc)})
            except OSError:
                self.respond(500, {"error": "Cannot save a run. Check the report directory permissions."})
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
        print(f"Reports saved locally in {app.directory.resolve()}. Ctrl-C stops the app.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
