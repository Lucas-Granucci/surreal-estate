"""User-facing property dashboard rendered from the shared results JSON contract."""

from html import escape

from surreal_estate.synthesis.frontend import FrontendResponse
from surreal_estate.synthesis.markdown import render_model_markdown


STYLE = """
:root{color-scheme:light;--ink:#203a35;--muted:#61736c;--line:#dce4dc;--paper:#fffefa;--green:#23654f}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:#f3f4ed;color:var(--ink);font:15px/1.65 system-ui,-apple-system,sans-serif}
a{color:var(--green);text-underline-offset:4px}a:hover{color:#123d30}
a:focus-visible,summary:focus-visible{outline:3px solid #b76b26;outline-offset:5px}
.skip{position:absolute;top:-100px;background:white;padding:12px}.skip:focus{top:8px;z-index:5}
.layout{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:100vh}
aside{padding:34px 24px;background:#183f34;color:#f2f5e9;position:sticky;top:0;height:100vh;overflow:auto}
.brand{font-size:18px;font-weight:750;letter-spacing:-.5px}.brand span{color:#c8dd95}
.eyebrow{text-transform:uppercase;letter-spacing:2px;font-size:11px;font-weight:700}
aside .eyebrow{color:#b5cbbd;margin-top:42px}nav a{display:block;color:#edf3e8;padding:10px 12px;border-radius:7px;text-decoration:none;margin:3px 0}
nav a:hover,nav a:focus{color:white;background:#305747}.nav-foot{border-top:1px solid #517064;margin-top:28px;padding-top:18px}
main{width:100%;max-width:1260px;padding:36px 48px 70px;margin:auto}
.topline{display:flex;justify-content:space-between;gap:16px;color:var(--muted);font-size:12px}
h1,h2,h3,p{overflow-wrap:anywhere}h1{font-family:Georgia,serif;font-size:clamp(30px,4vw,46px);line-height:1.16;letter-spacing:-1px;margin:18px 0}
h2{font-size:25px;letter-spacing:-.6px;margin:0 0 6px}h3{font-size:18px;margin:0 0 12px}p{margin:10px 0}
.muted{color:var(--muted)}.intro{max-width:680px}.tag{display:inline-block;padding:3px 9px;background:#edf1e8;border-radius:5px;font-size:12px;font-weight:650}
.tag.complete{background:#e1efdf;color:#27543c}.notice,.tag.error,.tag.blocked,.tag.truncated{background:#fff0d8;color:#754316}
.notice{padding:14px 18px;border-radius:8px;margin:18px 0;border:1px solid #e5d3af}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:28px 0 36px}
.metric{padding:20px;background:var(--paper);border:1px solid var(--line);border-radius:10px}.metric strong{display:block;font-size:32px;line-height:1.3;font-weight:550}.metric span{font-size:12px;color:var(--muted)}
section{margin:34px 0;scroll-margin-top:24px}.section-head{margin-bottom:18px}.card{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:24px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid .card{margin:0}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:16px;flex-wrap:wrap}
.model{overflow-wrap:anywhere}.model h1{font:700 25px/1.3 system-ui;letter-spacing:0}.model h2{font-size:21px;margin-top:24px}.model h3{margin-top:20px}
.model blockquote{border-left:3px solid #b2c99b;margin:18px 0;padding:0 18px;color:var(--muted)}
.model table{display:block;overflow:auto}.model img{max-width:100%}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted)}
.scroll{overflow:auto}details{border-top:1px solid var(--line);padding:15px 0 0;margin-top:18px}summary{cursor:pointer;font-weight:650}details[open]>summary{margin-bottom:16px}
pre{background:#edf0e8;border-radius:8px;padding:16px;max-height:480px;overflow:auto;font-size:12px;white-space:pre;line-height:1.6}code{overflow-wrap:anywhere}
.sources{list-style:none;padding:0;counter-reset:source}.sources li{padding:12px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.source-meta{font-size:12px;color:var(--muted)}
blockquote{margin:14px 0;padding-left:16px;border-left:3px solid #cdd8c7;overflow-wrap:anywhere}iframe{width:100%;height:240px;border:1px solid var(--line);border-radius:8px;background:white}
footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);overflow-wrap:anywhere}
@media(max-width:1100px){main{padding:30px 26px}.layout{grid-template-columns:210px minmax(0,1fr)}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:760px){.layout{display:block}aside{position:static;height:auto;padding:20px}aside .eyebrow{margin-top:16px}nav{display:flex;flex-wrap:wrap}nav a{padding:6px 10px;font-size:13px}.nav-foot{margin-top:12px;padding-top:10px}main{padding:24px 18px}.grid{grid-template-columns:1fr}.card{padding:18px}.topline{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""


def label(value: str) -> str:
    return escape(value.replace("_", " ").capitalize())


def raw_details(title: str, value) -> str:
    import json

    data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return f"<details><summary>{escape(title)}</summary><pre>{escape(json.dumps(data, indent=2, ensure_ascii=False))}</pre></details>"


def source_link(uri, title: str) -> str:
    if not uri:
        return escape(title or "Source URL unavailable")
    return f'<a href="{escape(str(uri), quote=True)}" target="_blank" rel="noreferrer noopener">{escape(title or str(uri))}</a>'


def render_amenity_members(item) -> str:
    """Keep individual map objects out of the default report reading flow."""
    if item.provider != "openstreetmap" or not isinstance(item.details.get("members"), list):
        return ""
    members = item.details["members"]
    if not members:
        return ""
    rows = []
    for member in members:
        if not isinstance(member, dict):
            continue
        kind, identifier = member.get("object_type"), member.get("object_id")
        if (
            kind not in {"node", "way", "relation"}
            or type(identifier) is not int
            or identifier <= 0
        ):
            continue
        uri = f"https://www.openstreetmap.org/{kind}/{identifier}"
        distance = member.get("approximate_center_distance_m")
        proximity = (
            f" · about {distance} m to point/center"
            if type(distance) is int and distance >= 0
            else ""
        )
        rows.append(
            "<li>"
            + source_link(uri, str(member.get("name") or "Unnamed mapped feature"))
            + escape(proximity)
            + "</li>"
        )
    return (
        '<details class="amenity-members"><summary>Supporting map features · '
        + str(len(rows))
        + "</summary><ul>"
        + "".join(rows)
        + "</ul></details>"
    )


def render_dashboard(payload: FrontendResponse) -> str:
    """Accept both transient responses and validated DevelopmentSnapshot objects."""
    report = payload.report
    topics = list(
        dict.fromkeys(
            [
                *report.case.priorities,
                *(item.topic for item in payload.web),
                *(item.topic for item in report.result.coverage),
                *(item.topic for item in report.result.observations),
            ]
        )
    )
    evidence = {item.id: item for item in report.result.evidence}
    urls = {str(item.uri) for item in evidence.values()}
    urls.update(
        str(chunk.uri) for item in payload.web for chunk in item.response.chunks if chunk.uri
    )
    complete = sum(item.status == "complete" for item in report.result.coverage)
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(report.case.address)} · Surreal Estate</title><style>{STYLE}</style></head><body>",
        '<a class="skip" href="#overview">Skip to property report</a><div class="layout"><aside>',
        '<div class="brand">surreal<span> estate.</span></div><p class="eyebrow">Property intelligence</p>',
        '<nav aria-label="Report sections"><a href="#overview">Overview</a><a href="#findings">Supported observations</a>',
        *(f'<a href="#topic-{i}">{label(topic)}</a>' for i, topic in enumerate(topics)),
        '<a href="#sources">Evidence library</a><a href="#coverage">Research coverage</a><a href="#data">Report data</a></nav>',
        '<nav class="nav-foot" aria-label="Tools"><a href="./">Debug dashboard ↗</a><a href="result.json">Open results JSON ↗</a></nav></aside>',
        '<main id="overview"><div class="topline"><span class="eyebrow">Your property report</span>',
        f"<span>As of {report.case.as_of:%b %d, %Y}</span></div>",
        f'<h1>{escape(report.case.address)}</h1><p class="muted">{escape(report.case.geography)}</p>',
        '<p class="intro">Explore the research behind this address. Read the findings, compare search responses with their re-checks, and follow each source.</p>',
    ]
    if report.demo:
        parts.append(
            '<div class="notice"><strong>Synthetic demo</strong> — not findings about this property or Pittsburgh.</div>'
        )
    parts.append('<div class="metrics">')
    for count, title in [
        (len(report.claims), "Supported observations"),
        (len(urls), "Unique source links"),
        (len(payload.web), "Search & re-check responses"),
        (f"{complete}/{len(report.result.coverage)}", "Research steps completed"),
    ]:
        parts.append(f'<div class="metric"><strong>{count}</strong><span>{title}</span></div>')
    parts.append(
        '</div><section id="findings"><div class="section-head"><h2>Supported observations</h2><p class="muted">Dossier findings with their evidence and qualifications.</p></div>'
    )
    if not report.claims:
        parts.append(
            '<div class="card"><h3>No supported observations yet</h3><p class="muted">Available model summaries are below. A completed search does not establish a verified finding.</p></div>'
        )
    for claim in report.claims:
        parts.append(
            f'<article class="card"><span class="tag">{label(claim.qualifier)}</span><p>{escape(claim.statement)}</p>'
        )
        if claim.flags:
            parts.append('<p class="muted">' + escape(" · ".join(claim.flags)) + "</p>")
        for evidence_id in claim.evidence_ids:
            item = evidence.get(evidence_id)
            if item:
                parts.append(f"<p>{source_link(item.uri, item.title)}</p>")
        attributions = sorted(
            {
                evidence[eid].attribution
                for eid in claim.evidence_ids
                if eid in evidence and evidence[eid].attribution
            }
        )
        for attribution in attributions:
            parts.append('<p class="source-meta">' + escape(attribution) + "</p>")
        for evidence_id in claim.evidence_ids:
            if evidence_id in evidence:
                parts.append(render_amenity_members(evidence[evidence_id]))
        parts.append(raw_details("Inspect provenance", claim) + "</article>")
    parts.append("</section>")
    for index, topic in enumerate(topics):
        entries = [(i, item) for i, item in enumerate(payload.web) if item.topic == topic]
        parts.append(
            f'<section id="topic-{index}"><div class="section-head"><p class="eyebrow">Research topic {index + 1:02d}</p><h2>{label(topic)}</h2></div>'
        )
        if entries:
            parts.append(
                '<p class="muted">Model-reported content. Re-checks are model assessments, not independently verified dossier evidence.</p>'
            )
        else:
            records = [o for o in report.result.observations if o.topic == topic]
            if records:
                parts.append(f'<div class="card"><h3>{len(records)} structured records</h3>')
                for observation in records:
                    for evidence_id in observation.evidence_ids:
                        item = evidence.get(evidence_id)
                        if item is None:
                            continue
                        parts.append("<details><summary>" + escape(item.title) + "</summary>")
                        parts.append("<p>" + escape(observation.statement) + "</p>")
                        parts.append("<p>" + source_link(item.uri, "View source") + "</p>")
                        parts.append(
                            '<p class="source-meta">' + escape(item.attribution or "") + "</p>"
                        )
                        parts.append(
                            raw_details("Structured fields and provenance", item) + "</details>"
                        )
                parts.append("</div>")
            else:
                parts.append(
                    '<div class="card"><p>No web response available for this topic.</p></div>'
                )
        for i, entry in entries:
            response = entry.response
            heading = "Claim re-check" if entry.label == "model_assessment" else "Original search"
            parts.append(
                f'<article class="card"><div class="card-head"><h3>{heading}</h3><span class="tag">{label(entry.label)}</span></div><p class="source-meta">{escape(entry.stage)} · {label(response.provider)}</p>'
            )
            if response.truncated:
                parts.append(
                    '<p class="notice">This response was truncated. Some content may be missing.</p>'
                )
            parts.append(
                '<div class="model">'
                + render_model_markdown(response.text or "No response text returned.")
                + "</div>"
            )
            parts.append(
                f'<details><summary>Sources & citation mapping · {len(response.chunks)} source slots</summary><ol class="sources">'
            )
            for j, chunk in enumerate(response.chunks):
                parts.append(
                    f'<li id="web-{i}-source-{j}"><span class="tag">{j + 1}</span> {source_link(chunk.uri, chunk.title)}</li>'
                )
            if not response.chunks:
                parts.append("<li>No source links returned.</li>")
            parts.append("</ol><h4>Supported passages</h4>")
            for support in response.supports:
                parts.append(
                    f'<blockquote>{escape(support.text)}<p class="source-meta">Response offsets {support.start_index}–{support.end_index} · Sources: '
                )
                refs = [
                    f'<a href="#web-{i}-source-{j}">{j + 1}</a>'
                    if 0 <= j < len(response.chunks)
                    else f"Unavailable (index {j})"
                    for j in support.chunk_indices
                ]
                parts.append(", ".join(refs) + "</p></blockquote>")
            if not response.supports:
                parts.append('<p class="muted">No citation mappings returned.</p>')
            parts.append("</details>")
            if response.search_queries:
                parts.append(
                    "<details><summary>Search queries</summary><ul>"
                    + "".join(f"<li>{escape(query)}</li>" for query in response.search_queries)
                    + "</ul></details>"
                )
            if response.search_entry_point:
                parts.append(
                    '<p class="source-meta">Google Search Suggestions</p><iframe title="Google Search Suggestions" referrerpolicy="no-referrer" sandbox="allow-popups allow-popups-to-escape-sandbox" srcdoc="'
                    + escape(response.search_entry_point, quote=True)
                    + '"></iframe>'
                )
            parts.append(raw_details("Inspect complete response", entry) + "</article>")
        observations = [item for item in report.result.observations if item.topic == topic]
        if observations:
            parts.append(
                raw_details(
                    "Inspect underlying observations",
                    [item.model_dump(mode="json") for item in observations],
                )
            )
        coverage = [item for item in report.result.coverage if item.topic == topic]
        for item in coverage:
            parts.append(
                f'<p><span class="tag {item.status}">{label(item.status)}</span> {escape(item.reason)}</p>'
            )
        parts.append("</section>")
    parts.append(
        '<section id="sources"><h2>Evidence library</h2><p class="muted">Dossier evidence. Web sources remain attached to their original responses above.</p><div class="grid">'
    )
    for item in evidence.values():
        parts.append(
            f'<article class="card"><span class="tag">{label(item.kind)}</span><h3>{source_link(item.uri, item.title)}</h3><p>{escape(item.excerpt)}</p><p class="source-meta">{escape(item.provider)} · Retrieved {item.retrieved_at:%b %d, %Y}</p>'
            + '<p class="source-meta">'
            + escape(item.attribution or "")
            + "</p>"
            + '<p class="source-meta">Source updated: '
            + escape(item.source_updated_at or "Not supplied")
            + " · Record date: "
            + escape(item.record_date or "Not supplied")
            + "</p>"
            + raw_details("Inspect evidence record", item)
            + "</article>"
        )
    if not evidence:
        parts.append('<p class="muted">No dossier evidence returned.</p>')
    parts.append(
        '</div></section><section id="coverage"><h2>Research coverage</h2><p class="muted">What was attempted, what returned, and what remains unavailable.</p><div class="card scroll"><table><thead><tr><th>Topic / channel</th><th>Status</th><th>Details</th><th>Queries / sources</th></tr></thead><tbody>'
    )
    for item in report.result.coverage:
        parts.append(
            f'<tr><td>{label(item.topic)}<br><span class="source-meta">{escape(item.channel)} · {escape(item.provider or "Provider not specified")}</span></td><td><span class="tag {item.status}">{label(item.status)}</span></td><td>{escape(item.reason)}</td><td>{item.queries_run} / {item.sources_returned}</td></tr>'
        )
    if not report.result.coverage:
        parts.append('<tr><td colspan="4">No coverage information available.</td></tr>')
    parts.append("</tbody></table></div>")
    if report.plan:
        parts.append(
            '<div class="card"><h3>Research scope</h3><p>Channels: '
            + escape(", ".join(report.plan.channels))
            + "</p>"
        )
        for query in report.plan.queries:
            parts.append(
                f'<p><strong>{label(query.topic)}</strong> · {escape(query.geography)}<br><span class="muted">{query.start_date} to {query.end_date} · {escape(", ".join(query.source_types))}</span></p>'
            )
        parts.append(raw_details("Inspect research plan", report.plan) + "</div>")
    else:
        parts.append('<p class="muted">No validated research plan available.</p>')
    parts.append(
        '</section><section id="data"><h2>Report data</h2><p class="muted">All fields from the results JSON, preserved for inspection.</p><div class="card">'
    )
    parts.append(raw_details("Explore full results JSON", payload))
    parts.append(
        f"</div></section><footer>Run {escape(report.id)} · Schema {escape(payload.schema_version)}<br>This local viewer expires after its configured lifetime. Saved development JSON files remain on disk.</footer></main></div></body></html>"
    )
    return "\n".join(parts)
