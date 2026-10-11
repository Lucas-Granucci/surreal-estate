"""Escaped, read-only inspector for the run-local debug log."""

import json
from html import escape

from surreal_estate.orchestrator.debug import DebugEvent


def pretty(value) -> str:
    return escape(json.dumps(value, indent=2, ensure_ascii=False))


def render_debug(events: list[DebugEvent]) -> str:
    parts = [
        "<section id='debug'><h2>Debug · data flow</h2>",
        (
            "<p>Follow each numbered step from request to response to validated output. "
            "API keys are redacted; these details live only in this process.</p>"
        ),
    ]
    if not events:
        parts.append(
            "<p>No model calls recorded. The offline demo uses deterministic fixtures.</p>"
        )
    parts.append("<nav aria-label='Debug steps'>")
    for event in events:
        parts.append(
            f"<a class='step-link' href='#step-{event.sequence}'>{event.sequence}. {escape(event.stage)}</a> "
        )
    parts.append("</nav>")
    for event in events:
        parts.append(
            f"<details class='debug-step' id='step-{event.sequence}' open><summary>"
            f"{event.sequence}. {escape(event.stage)} "
            f"<span class='badge {escape(event.status)}'>{escape(event.status)}</span>"
            f" <span class='muted'>+{event.started_seconds:.2f}s · {event.duration_seconds:.2f}s"
            + (f" · HTTP {event.http_status}" if event.http_status else "")
            + "</span></summary>"
        )
        if event.error:
            parts.append(f"<p class='error'>{escape(event.error)}</p>")
        body = event.request.get("body", {})
        model = event.request.get("model", body.get("model"))
        if model:
            parts.append(f"<p><strong>Model:</strong> {escape(model)}</p>")
        if event.request.get("endpoint"):
            parts.append(f"<p class='muted'>POST {escape(event.request['endpoint'])}</p>")
        parts.append("<div class='debug-columns'><div><h3>1 · Input / prompt</h3>")
        for message in body.get("messages", []):
            parts.append(
                f"<h4>{escape(message.get('role', 'message'))}</h4>"
                f"<pre>{escape(message.get('content', ''))}</pre>"
            )
        for content in body.get("contents", []):
            for part in content.get("parts", []):
                if "text" in part:
                    parts.append(f"<pre>{escape(part['text'])}</pre>")
        parts.append(
            "<details><summary>Exact request JSON (without authentication headers)</summary><pre>"
            + pretty(event.request)
            + "</pre></details></div><div><h3>2 · Provider output</h3>"
        )
        response = event.response
        if isinstance(response, dict) and isinstance(response.get("message"), dict):
            content = response["message"].get("content", "")
            try:
                rendered = pretty(json.loads(content))
            except (ValueError, TypeError):
                rendered = escape(content)
            parts.append("<pre>" + rendered + "</pre>")
        elif isinstance(response, dict) and response.get("candidates"):
            parts.append(
                "<p>Gemini's answer and Search Suggestions are displayed above. "
                "Expand the response to inspect text, search queries, source chunks, "
                "support mappings, finish reason, and token usage.</p>"
            )
        elif response is None:
            parts.append(
                "<p>No provider response (local stage or request failed before a response).</p>"
            )
        parts.append(
            "<details><summary>Full response JSON</summary><pre>"
            + pretty(response)
            + "</pre></details>"
        )
        parts.append(
            "<h3>3 · Parsed output / handoff</h3><pre>"
            + pretty(event.parsed)
            + "</pre></div></div></details>"
        )
    return "\n".join(parts) + "</section>"
