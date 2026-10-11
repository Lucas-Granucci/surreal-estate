"""Loopback-only, no-store display. No templates, logs, disk exports, or URL fetching."""

from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from secrets import token_urlsafe
from time import monotonic

from surreal_estate.orchestrator.runner import RunOutcome
from surreal_estate.synthesis.debug_view import pretty, render_debug
from surreal_estate.synthesis.dashboard import render_dashboard
from surreal_estate.synthesis.frontend import build_frontend_response
from surreal_estate.synthesis.markdown import render_model_markdown
from surreal_estate.synthesis.sources_view import render_sources


def render_html(outcome: RunOutcome) -> str:
    report = outcome.report
    parts = [
        (
            "<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'><title>Property research</title>"
        ),
        """<style>
        body{font:16px/1.6 system-ui,sans-serif;background:#f4f6f8;color:#182636;margin:0}
        main{max-width:1100px;margin:40px auto;padding:0 24px} h1{margin-bottom:0}
        section,details{background:white;border:1px solid #d9e0e6;border-radius:12px;padding:24px;margin:20px 0}
        h2{margin-top:0;font-size:21px} a{color:#075cab} pre{white-space:pre-wrap;overflow-wrap:anywhere}
        table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:12px;border-bottom:1px solid #e4e9ed;vertical-align:top}
        .scroll{overflow-x:auto}.badge{padding:3px 9px;background:#edf1f5;border-radius:6px;white-space:nowrap}
        .error,.blocked,.truncated{background:#fff0db;color:#7b3600}.complete{background:#e0f4e8;color:#145b35}
        .muted{color:#596b7b} li{margin:8px 0}summary{cursor:pointer;font-weight:600}
        .debug-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}
        .debug-step{border-left:4px solid #397fa7}.debug-step pre{max-height:520px;overflow:auto;background:#f5f7fa;padding:16px;font-size:13px}
        .debug-step details{padding:12px}.step-link{display:inline-block;padding:8px 12px;margin:4px;background:#edf1f5;border-radius:6px}
        .model-markdown{overflow-wrap:anywhere}.model-markdown h1{font-size:26px;margin:20px 0 12px}
        .model-markdown h2{font-size:22px;margin:20px 0 12px}.model-markdown h3{font-size:18px}
        .model-markdown blockquote{border-left:4px solid #ccd8e2;margin:16px 0;padding:4px 16px;color:#596b7b}
        .model-markdown pre{padding:16px;background:#f5f7fa;border-radius:8px;overflow:auto}
        .model-markdown code{background:#f5f7fa;padding:2px 4px;border-radius:4px}
        .model-markdown table{display:block;overflow-x:auto;font-size:14px}
        .json-block{max-height:650px;overflow:auto;white-space:pre;tab-size:2;background:#f5f7fa;padding:16px;font-size:13px;border-radius:8px}
        .source-channels{display:grid;grid-template-columns:1fr 1fr 2fr;gap:24px;overflow-wrap:anywhere}
        .source-channels h3{margin-top:0;font-size:17px}.source-channels details{padding:12px;margin:12px 0}
        @media(max-width:800px){.source-channels{grid-template-columns:1fr}}
        @media(max-width:800px){.debug-columns{grid-template-columns:1fr}section,details{padding:16px}}
        </style><main><p class='muted'>SURREAL ESTATE · RUN REVIEW</p><h1>Property research</h1>""",
        f"<p>{escape(report.case.address)} · As of {report.case.as_of}</p>",
        "<p class='muted'>Completed run snapshot. Results remain available while this process runs.</p>",
        (
            '<nav><a class="step-link" href="__DASHBOARD_URL__">Open property dashboard →</a>'
            "<a class='step-link' href='#debug'>Inspect prompts &amp; responses ↓</a>"
            "<a class='step-link' href='#frontend-json'>View full JSON ↓</a></nav>"
        ),
    ]
    if report.demo:
        parts.append(
            "<p><strong>SYNTHETIC DEMO — not findings about this property or Pittsburgh.</strong></p>"
        )
    parts.append(render_sources(outcome))
    parts.append("<section><h2>Research plan</h2>")
    if report.plan:
        parts.append("<p>" + escape(" → ".join(report.plan.channels)) + "</p><ul>")
        for query in report.plan.queries:
            parts.append(
                f"<li><strong>{escape(query.topic)}</strong> · {escape(query.geography)}<br>"
                f"{query.start_date} – {query.end_date} · {escape(', '.join(query.source_types))}</li>"
            )
        parts.append("</ul>")
    else:
        parts.append("<p>No validated plan available. See coverage below.</p>")
    parts.append(
        "</section><section><h2>Pipeline coverage</h2><div class='scroll'><table>"
        "<thead><tr><th>Channel / topic</th><th>Status</th><th>Details</th></tr></thead><tbody>"
    )
    for item in report.result.coverage:
        parts.append(
            f"<tr><td>{escape(item.channel)} / {escape(item.topic)}</td>"
            f"<td><span class='badge {item.status}'>{escape(item.status)}</span></td>"
            f"<td>{escape(item.reason)}</td></tr>"
        )
    parts.append("</tbody></table></div></section><section><h2>Supported observations</h2>")
    evidence = {e.id: e for e in report.result.evidence}
    if not report.claims:
        parts.append("<p>No supported observations available.</p>")
    for claim in report.claims:
        parts.append(
            f"<p><span class='badge'>{escape(claim.qualifier)}</span> {escape(claim.statement)}</p><ul>"
        )
        for evidence_id in claim.evidence_ids:
            item = evidence[evidence_id]
            parts.append(
                f'<li><a rel="noreferrer noopener" href="{escape(str(item.uri), quote=True)}">{escape(item.title)}</a></li>'
            )
            if item.attribution:
                parts.append("<li class='muted'>" + escape(item.attribution) + "</li>")
        parts.append("</ul><p class='muted'>" + escape(", ".join(claim.flags)) + "</p>")
    parts.append("</section><details open><summary>Execution trace</summary><ol>")
    parts.extend(f"<li>{escape(event)}</li>" for event in report.trace)
    parts.append("</ol></details>")
    for display in outcome.displays:
        response = display.response
        parts.append(f"<p class='muted'>{escape(display.topic)} · {escape(display.stage)}</p>")
        parts.append(
            "<section><h2>Model-reported summary of search results</h2>"
            "<p>Transient Gemini response; not verified dossier evidence.</p>"
        )
        parts.append(
            "<div class='model-markdown'>" + render_model_markdown(response.text) + "</div>"
        )
        parts.append("<ul>")
        for i, chunk in enumerate(response.chunks):
            if chunk.uri:
                parts.append(
                    f'<li>{i + 1}. <a rel="noreferrer noopener" href="{escape(str(chunk.uri), quote=True)}">'
                    + escape(chunk.title or str(chunk.uri))
                    + "</a></li>"
                )
        parts.append("</ul>")
        # Provider HTML is untrusted active content. Preserve it inside a sandbox,
        # without script or same-origin permissions, rather than injecting into the page.
        parts.append(
            '<iframe title="Google Search Suggestions" style="width:100%;height:240px" '
            'referrerpolicy="no-referrer" sandbox="allow-popups allow-popups-to-escape-sandbox" '
            'srcdoc="' + escape(response.search_entry_point, quote=True) + '"></iframe></section>'
        )
    payload = build_frontend_response(outcome)
    parts.append(
        "<details id='frontend-json'><summary>Frontend response JSON · includes web-channel data</summary>"
        "<pre class='json-block'>" + pretty(payload.model_dump(mode="json")) + "</pre></details>"
    )
    if outcome.snapshot_path:
        parts.append(
            "<p class='muted'>Saved development JSON: " + escape(outcome.snapshot_path) + "</p>"
        )
    parts.append(render_debug(outcome.debug_events))
    return "\n".join(parts) + "</main></html>"


class TransientView:
    """Bounded lifetime; a frontend acknowledgement releases both display buffers."""

    def __init__(self, outcome: RunOutcome, ttl_seconds: float = 900):
        if ttl_seconds <= 0:
            raise ValueError("Display lifetime must be positive")
        self.html = render_html(outcome).encode()
        self.dashboard = render_dashboard(build_frontend_response(outcome)).encode()
        self.json = build_frontend_response(outcome).model_dump_json(indent=2).encode()
        self.expires_at = monotonic() + ttl_seconds

    @property
    def active(self):
        if monotonic() >= self.expires_at:
            self.release()
        return self.json is not None

    def release(self):
        self.html = None
        self.dashboard = None
        self.json = None


def display_handler(view: TransientView, token: str):

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            routes = {
                "/" + token: (view.html, "text/html; charset=utf-8"),
                "/" + token + "/": (view.html, "text/html; charset=utf-8"),
                "/" + token + "/dashboard": (view.dashboard, "text/html; charset=utf-8"),
                "/" + token + "/result.json": (view.json, "application/json; charset=utf-8"),
            }
            if self.path not in routes:
                self.respond(404)
                return
            if not view.active:
                self.respond(410)
                return
            body, content_type = routes[self.path]
            if content_type.startswith("text/html") and body is not None:
                body = body.replace(b"__DASHBOARD_URL__", ("/" + token + "/dashboard").encode())
            self.respond(200, body, content_type)

        def do_POST(self):
            if self.path != "/" + token + "/release":
                self.respond(404)
                return
            view.release()
            self.respond(204)

        def respond(self, status, body=b"", content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; frame-src 'self' about:; img-src https: data:; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def serve(outcome: RunOutcome, port: int = 8765, ttl_seconds: float = 900):
    view = TransientView(outcome, ttl_seconds)
    token = token_urlsafe(24)
    Handler = display_handler(view, token)
    with HTTPServer(("127.0.0.1", port), Handler) as server:
        server.timeout = 0.5
        print(f"Transient results: http://127.0.0.1:{server.server_port}/{token}", flush=True)
        print(f"Property dashboard: http://127.0.0.1:{server.server_port}/{token}/dashboard", flush=True)
        print(
            f"Frontend JSON: http://127.0.0.1:{server.server_port}/{token}/result.json", flush=True
        )
        print(
            f"POST /{token}/release after viewing to discard this run; expires after {ttl_seconds:g} seconds.",
            flush=True,
        )
        print(
            f"For SSH: forward local port {server.server_port} to 127.0.0.1:{server.server_port} on this host.",
            flush=True,
        )
        print("Ctrl-C closes the viewer and releases the in-memory responses.", flush=True)
        try:
            while view.active:
                server.handle_request()
        except KeyboardInterrupt:
            pass
        finally:
            view.release()
