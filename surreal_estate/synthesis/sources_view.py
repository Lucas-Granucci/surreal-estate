"""Current-run source inventory; never infer sources from plans or prompt examples."""

from html import escape
from urllib.parse import urlsplit

from surreal_estate.orchestrator.runner import RunOutcome


def source_link(uri, title):
    return (
        f'<a href="{escape(str(uri), quote=True)}" rel="noreferrer noopener">'
        + escape(title or str(uri))
        + "</a>"
    )


def render_sources(outcome: RunOutcome) -> str:
    result = outcome.report.result
    api_evidence = [e for e in result.evidence if e.kind == "official_record"]
    providers = sorted(
        {e.provider for e in api_evidence}
        | {c.provider for c in result.coverage if c.channel == "apis" and c.provider}
    )
    parts = [
        "<section id='run-sources'><h2>Sources for this run</h2><div class='source-channels'>",
        "<div><h3>Channel A · APIs</h3>",
    ]
    if not providers:
        parts.append("<p>No API evidence returned or provider attempts recorded.</p>")
    else:
        parts.append("<ul>")
        for provider in providers:
            name = {"census": "U.S. Census Geocoder"}.get(provider, provider)
            items = [e for e in api_evidence if e.provider == provider]
            statuses = sorted(
                {
                    c.status
                    for c in result.coverage
                    if c.channel == "apis" and c.provider == provider
                }
            )
            parts.append(
                "<li><strong>"
                + escape(name)
                + "</strong>"
                + (" · " + escape(", ".join(statuses)) if statuses else "")
            )
            if items:
                parts.append("<ul>")
                seen = set()
                for item in items:
                    if str(item.uri) not in seen:
                        parts.append("<li>" + source_link(item.uri, item.title) + "</li>")
                        seen.add(str(item.uri))
                parts.append("</ul>")
            else:
                parts.append("<p class='muted'>Attempt recorded; no evidence returned.</p>")
            parts.append("</li>")
        parts.append("</ul>")
    parts.append("</div><div><h3>Channel B · User-provided files</h3>")
    uploads = [e for e in result.evidence if e.kind == "user_document"]
    if uploads:
        parts.append("<ul>")
        parts.extend("<li>" + source_link(e.uri, e.title) + "</li>" for e in uploads)
        parts.append("</ul>")
    else:
        parts.append(
            "<p>No uploaded documents, photos or floorplans recorded.</p>"
            "<p class='muted'>Upload and extraction flow is not yet implemented.</p>"
        )
    parts.append("</div><div><h3>Channel C · Open web</h3>")
    gemini = any(d.response.provider == "gemini_search" for d in outcome.displays)
    if gemini:
        parts.append("<p><strong>Gemini API + Google Search grounding</strong></p>")
        models = sorted(
            {
                e.request["model"]
                for e in outcome.debug_events
                if e.stage.startswith("Gemini") and e.request.get("model")
            }
        )
        if models:
            parts.append("<p class='muted'>Model: " + escape(", ".join(models)) + "</p>")
    refs = {}
    for display in outcome.displays:
        cited = {i for support in display.response.supports for i in support.chunk_indices}
        for index, chunk in enumerate(display.response.chunks):
            if chunk.uri is None:
                continue
            uri = str(chunk.uri)
            item = refs.setdefault(uri, {"title": chunk.title, "tags": set(), "cited": False})
            if not item["title"] and chunk.title:
                item["title"] = chunk.title
            item["tags"].add(display.topic + " · " + display.stage)
            item["cited"] |= index in cited
    # The offline fixture produces ordinary evidence instead of live display objects.
    for evidence in result.evidence:
        if evidence.kind in {"reported", "synthetic"}:
            refs.setdefault(
                str(evidence.uri),
                {"title": evidence.title, "tags": {evidence.provider}, "cited": True},
            )
    if refs:
        domains = sorted({urlsplit(uri).hostname or "unknown" for uri in refs})
        parts.append("<p>Returned link domains: " + escape(", ".join(domains)) + "</p>")
        cited_count = sum(item["cited"] for item in refs.values())
        parts.append(
            f"<details><summary>{len(refs)} source links · {cited_count} cited</summary><ul>"
        )
        for uri, item in refs.items():
            parts.append(
                "<li>"
                + source_link(uri, item["title"])
                + "<br><span class='muted'>"
                + escape("; ".join(sorted(item["tags"])))
                + (" · cited" if item["cited"] else " · returned without a support mapping")
                + "</span></li>"
            )
        parts.append(
            "</ul></details><p class='muted'>Source pages were not fetched by this application. "
            "Domains reflect returned URLs, including provider redirects.</p>"
        )
    else:
        parts.append("<p>No web source links available for display in this run.</p>")
    return "".join(parts) + "</div></div></section>"
