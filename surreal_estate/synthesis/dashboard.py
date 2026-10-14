"""User-facing property dashboard rendered from the shared results JSON contract."""

from html import escape
from importlib.resources import files
from urllib.parse import urlencode

from surreal_estate.synthesis.frontend import FrontendResponse
from surreal_estate.synthesis.markdown import render_model_markdown
from surreal_estate.synthesis.report_visuals import nearby_map, closure_timeline, closure_details


# Keep the report and research form on the same design system.

STYLE = files("surreal_estate.webapp").joinpath("static", "app.css").read_text()


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


def section_start(identifier: str, title: str, subtitle: str, *, expanded: bool = False) -> str:
    return (
        f'<section id="{escape(identifier, quote=True)}"><details class="report-section"'
        + (' open' if expanded else '')
        + f'><summary><h2>{escape(title)}</h2><span class="section-meta">{escape(subtitle)}</span></summary><div class="section-body">'
    )


def topic_summary(topic: str, payload: FrontendResponse) -> str:
    responses = sum(item.topic == topic for item in payload.web)
    records = sum(item.topic == topic for item in payload.report.result.observations)
    statuses = list(dict.fromkeys(item.status.replace("_", " ") for item in payload.report.result.coverage if item.topic == topic))
    counts = []
    if responses:
        counts.append(f"{responses} web research responses")
    if records:
        counts.append(f"{records} recorded observations")
    return " · ".join([*counts, *statuses]) or "No results available"


def coverage_summary(coverage, topic_indices) -> str:
    included = [item for item in coverage if item.reason not in {"Not selected for this run", "Not selected by planner"}]
    buckets = [
        ("complete", "Completed", [item for item in included if item.status == "complete"]),
        ("blocked", "Blocked", [item for item in included if item.status == "blocked"]),
        ("error", "Errors", [item for item in included if item.status == "error"]),
        ("partial", "Partial / no results", [item for item in included if item.status not in {"complete", "blocked", "error"}]),
    ]
    total = len(included)
    completed = len(buckets[0][2])
    description = ", ".join(f"{len(items)} {title.lower()}" for _, title, items in buckets)
    parts = [f'<div class="coverage-overview" aria-labelledby="coverage-title"><div class="coverage-heading"><h2 id="coverage-title">Research coverage</h2><a href="#coverage">See all steps ↗</a></div><p><strong>{completed}/{total}</strong> selected research steps completed</p>']
    if not total:
        parts.append('<p class="muted">No coverage information available.</p>')
    parts.append(f'<div class="coverage-meter" role="img" aria-label="{escape(description)}">')
    for status, title, items in buckets:
        if items:
            parts.append(f'<span class="coverage-segment {status}" style="width:{len(items) / max(total, 1) * 100:.2f}%"></span>')
    parts.append('</div><div class="coverage-counts">')
    for status, title, items in buckets:
        parts.append(f'<a href="#coverage" class="coverage-count {status}"><strong>{len(items)}</strong><span>{title}</span></a>')
    parts.append('</div>')
    attention = [item for item in included if item.status in {"blocked", "error"}]
    if attention:
        parts.append('<div class="coverage-attention"><span>Needs attention:</span>')
        for topic in dict.fromkeys(item.topic for item in attention):
            target = f"topic-{topic_indices[topic]}" if topic in topic_indices else "coverage"
            parts.append(f'<a href="#{target}">{label(topic)}</a>')
        parts.append('</div>')
    parts.append('<p class="source-meta">Completion describes research availability, not confidence in the property. Unselected channels are excluded.</p></div>')
    return ''.join(parts)


def parcel_choices(candidates, case, *, app_mode=False) -> str:
    parts = ['<div class="card parcel-choices"><h3>Choose the intended parcel</h3><p>These are distinct county records at the same address. Compare the parcel IDs and uses; none has been attached to this report.</p><div class="grid">']
    for candidate in candidates:
        parts.append('<article class="parcel-choice"><h4>' + escape(candidate.property_use) + '</h4><p><b>' + escape(candidate.parcel_id) + '</b></p><p>' + escape(candidate.address) + '</p>')
        parts.append('<p class="source-meta">Recorded lot area: ' + escape(candidate.lot_area or 'Not supplied') + ' sq ft<br>County assessment: ' + escape(candidate.assessed_value or 'Not supplied') + ' USD</p>')
        parts.append('<p>' + source_link(candidate.source_url, 'View county data') + '</p>')
        if app_mode:
            query = urlencode(dict(address=case.address, geography=case.geography, parcel_id=candidate.parcel_id))
            parts.append(f'<a class="pill" href="/?{escape(query, quote=True)}#research-form">Research this parcel ↗</a>')
        parts.append('</article>')
    parts.append('</div></div>')
    return ''.join(parts)


def render_dashboard(payload: FrontendResponse, *, app_mode: bool = False) -> str:
    """Accept both transient responses and validated DevelopmentSnapshot objects."""
    report = payload.report
    topics = list(
        dict.fromkeys(
            [
                *report.case.priorities,
                *(item.topic for item in payload.web),
                *(item.topic for item in report.result.coverage if item.reason != "Not selected for this run" and item.topic not in {"research", "plan"}),
                *(item.topic for item in report.result.observations),
            ]
        )
    )
    # One order drives both the sidebar and the actual report sections.
    topic_order = ["mapped_amenities", "amenities", "street_closures", "road_projects",
                   "neighborhood_discussion", "restaurant_reviews", "geocoding", "flood_hazard",
                   "flood_map_panels", "property_assessment", "building_permits"]
    ranks = {topic: index for index, topic in enumerate(topic_order)}
    topics.sort(key=lambda topic: ranks.get(topic, len(ranks)))
    evidence = {item.id: item for item in report.result.evidence}
    urls = {str(item.uri) for item in evidence.values()}
    urls.update(
        str(chunk.uri) for item in payload.web for chunk in item.response.chunks if chunk.uri
    )
    topic_titles = {
        "neighborhood_discussion": "What locals say", "restaurant_reviews": "Where to eat",
        "amenities": "Around the block", "mapped_amenities": "Around the block", "road_projects": "Street closures", "street_closures": "Street closures",
        "flood_hazard": "Flood hazard", "flood_map_panels": "Flood map details",
        "geocoding": "Address match", "property_assessment": "Property assessment",
        "building_permits": "Building permits",
    }
    topic_title = lambda topic: topic_titles.get(topic, topic.replace("_", " ").capitalize())
    gaps = [item for item in report.result.coverage
            if item.status != "complete" and item.reason != "Not selected for this run"]
    topic_indices = {topic: index for index, topic in enumerate(topics)}
    property_topics = {"geocoding", "property_assessment", "building_permits", "flood_hazard", "flood_map_panels"}
    neighborhood_topics = {"neighborhood_discussion", "restaurant_reviews", "mapped_amenities", "amenities", "street_closures", "road_projects"}
    navigation = ['<a href="#overview">Overview</a>']
    for group_title, group_topics in [("Neighborhood", neighborhood_topics), ("Property & records", property_topics), ("Other research", set(topics) - property_topics - neighborhood_topics)]:
        group = [topic for topic in topics if topic in group_topics]
        if group:
            navigation.append(f'<details class="nav-group" open><summary>{group_title}</summary>')
            navigation.extend(f'<a href="#topic-{topic_indices[topic]}">{escape(topic_title(topic))}</a>' for topic in group)
            navigation.append('</details>')
    navigation.append('<details class="nav-group"><summary>Report details</summary><a href="#gaps">What’s missing</a><a href="#findings">Supported observations</a><a href="#sources">Sources &amp; credits</a><a href="#coverage">Research coverage</a><a href="#data">Raw report data</a></details>')
    debug_url = "debug" if app_mode else "./"
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(report.case.address)} · SurrealEstate</title><style>{STYLE}</style>",
        '<script src="/app.js" defer></script>' if app_mode else "",
        '</head><body><a class="skip" href="#report-summary">Skip to property report</a>',
        '<header class="bar"><a class="logo" href="/">SurrealEstate<span class="logo-dot" aria-hidden="true"></span></a>',
        '<a class="pill" href="/">New address</a><a class="pill" href="/#history">Saved reports</a>' if app_mode else '',
        '</header><div class="hero report-hero" id="overview"><div class="hero-in"><div>',
        f'<div class="asof">Researched {report.case.as_of:%b %d, %Y}</div>',
        f'<h1>{escape(report.case.address)}</h1><p class="muted" style="margin-top:12px">{escape(report.case.geography)}</p>',
        '<p class="lede">Property facts, nearby places and local context. Follow any finding back to its source.</p>',
        '</div></div></div>',
        '<div class="shell"><nav class="rail" aria-label="Report sections"><button class="pill report-nav-toggle" type="button" aria-expanded="false" aria-controls="report-navigation" hidden>Browse report sections</button><div id="report-navigation"><p class="rail-title">In this report</p>',
        *navigation,
        '<div class="section-controls"><button type="button" class="pill" data-sections="expand">Expand all</button><button type="button" class="pill" data-sections="collapse">Collapse all</button></div>' if app_mode else '',
        f'<details class="nav-group nav-foot"><summary>Developer tools</summary><a href="{debug_url}">Debug dashboard ↗</a><a href="result.json">Open results JSON ↗</a></details></div></nav><main>',
        '<div class="legend">Reading this report <span class="tag t-off">Official records</span><span class="tag t-com">Community-mapped</span><span class="tag t-ai">Model-reported</span></div>',
    ]
    match = next((item for item in evidence.values() if item.provider == "census" and item.details.get("matched_address")), None)
    if match:
        match_label = "Confirmed address." if match.match_method == "user_confirmed_census_address_range_match" else "Check the match."
        parts.append('<div class="confirm"><span><b>' + match_label + '</b> ' + escape(str(match.details["matched_address"])) + '. Distances use an estimated address point, not the building.</span>' + ('<a class="pill" href="/">Fix address</a>' if app_mode else '') + '</div>')
    if report.demo:
        parts.append(
            '<div class="notice"><strong>Synthetic demo</strong> — not findings about this property or Pittsburgh.</div>'
        )
    parts.append('<div id="report-summary" class="report-summary" role="region" aria-labelledby="report-summary-title" tabindex="-1"><h2 id="report-summary-title">Explore this address</h2>')
    parts.append('<div class="report-overview-links">')
    for topic in ["mapped_amenities", "street_closures", "property_assessment", "neighborhood_discussion"]:
        if topic in topic_indices:
            parts.append(f'<a href="#topic-{topic_indices[topic]}">{escape(topic_title(topic))}</a>')
    parts.append('</div>')
    if report.claims:
        parts.append(f'<details><summary>{len(report.claims)} supported observations · preview findings</summary><ul class="finding-preview">')
        for claim in report.claims[:3]:
            parts.append('<li><span class="tag">' + label(claim.qualifier) + '</span><p>' + escape(claim.statement) + '</p>')
            if claim.flags:
                parts.append('<p class="source-meta">' + escape(' · '.join(claim.flags)) + '</p>')
            for evidence_id in claim.evidence_ids:
                if evidence_id in evidence:
                    item = evidence[evidence_id]
                    parts.append('<span class="finding-source">' + source_link(item.uri, item.title) + '</span>')
            parts.append('</li>')
        parts.append('</ul>')
        if len(report.claims) > 3:
            parts.append(f'<p class="source-meta">Showing the first 3 of {len(report.claims)} observations in report order.</p>')
        parts.append(f'<a href="#findings">Read all {len(report.claims)} supported observations</a></details>')
    else:
        parts.append('<p class="note">No supported observations yet. Topic sections contain available research; model summaries remain unverified.</p>')
    parts.append(f'<p class="summary-gap"><a href="#gaps">Review what we couldn’t check ({len(gaps)})</a>. Missing information does not establish that a property is free of issues.</p></div>')
    parts.append(f'<p class="report-stats">{len(urls)} source links · {len(payload.web)} web research responses</p>')
    parts.append('<details class="coverage-disclosure"><summary>Research availability · ' + str(len(gaps)) + ' gaps or empty results</summary>' + coverage_summary(report.result.coverage, topic_indices) + '</details>')
    lead_topic = next((topic for topic in topics if any(o.topic == topic for o in report.result.observations) or any(w.topic == topic for w in payload.web)), topics[0] if topics else None)
    for index, topic in enumerate(topics):
        entries = [(i, item) for i, item in enumerate(payload.web) if item.topic == topic]
        parts.append(
            section_start(f"topic-{index}", topic_title(topic), topic_summary(topic, payload), expanded=not app_mode or topic == lead_topic)
        )
        if topic == "mapped_amenities":
            parts.append(nearby_map(list(evidence.values()), interactive=app_mode))
        if topic == "street_closures":
            parts.append(closure_details(list(evidence.values())))
            timeline = closure_timeline(list(evidence.values()), report.case.as_of)
            if timeline:
                parts.append('<details><summary>Compare permit dates</summary>' + timeline + '</details>')
        if entries:
            parts.append(
                '<p class="muted">Model-reported content. Re-checks are model assessments, not independently verified dossier evidence.</p>'
            )
        else:
            records = [o for o in report.result.observations if o.topic == topic]
            if records:
                if topic in {"mapped_amenities", "street_closures"}:
                    parts.append('<details><summary>All recorded observations &amp; source details</summary>')
                parts.append(f'<div class="card"><h3>{len(records)} recorded observations</h3>')
                for observation in records:
                    parts.append('<article class="record-observation"><span class="tag">' + label(observation.qualifier) + '</span><p>' + escape(observation.statement) + '</p>')
                    if observation.flags:
                        parts.append('<p class="source-meta">' + escape(' · '.join(observation.flags)) + '</p>')
                    for evidence_id in observation.evidence_ids:
                        item = evidence.get(evidence_id)
                        if item is None:
                            continue
                        parts.append("<p>" + source_link(item.uri, item.title) + "</p>")
                        parts.append(
                            '<p class="source-meta">' + escape(item.attribution or "") + "</p>"
                        )
                        parts.append(
                            raw_details("Record details & provenance", item)
                        )
                    parts.append('</article>')
                parts.append("</div>")
                if topic in {"mapped_amenities", "street_closures"}:
                    parts.append('</details>')
            else:
                message = "No web response available for this topic." if topic in {"neighborhood_discussion", "restaurant_reviews"} else "No structured results available. See the coverage reason below."
                parts.append(f'<div class="card"><p>{message}</p></div>')
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
            if item.parcel_candidates:
                parts.append(parcel_choices(item.parcel_candidates, report.case, app_mode=app_mode))
            if item.provider == "fema_nfhl" and item.status in {"error", "truncated"}:
                parts.append('<p><a href="https://msc.fema.gov/portal/home" target="_blank" rel="noopener noreferrer">Open FEMA’s Map Service Center ↗</a></p>')
            parts.append(
                f'<p><span class="tag {item.status}">{label(item.status)}</span> {escape(item.reason)}</p>'
            )
        parts.append("</div></details></section>")
    parts.append(section_start("gaps", "What we couldn’t check", f"{len(gaps)} gaps or empty results. A gap is not good news.", expanded=not app_mode) + '<div class="card">')
    for item in gaps:
        parts.append(f'<div class="coverage-gap"><span class="tag {item.status}">{label(item.status)}</span><p><b>{label(item.topic)}</b> · {escape(item.reason)}</p></div>')
    if not gaps:
        parts.append('<p>No incomplete steps reported for the selected research scope.</p>')
    parts.append('</div></div></details></section>')
    parts.append(
        section_start("findings", "Supported observations", "Dossier findings with their evidence and qualifications.", expanded=not app_mode)
    )
    if not report.claims:
        parts.append(
            '<div class="card"><h3>No supported observations yet</h3><p class="muted">Explore the topic sections for available model summaries. A completed search does not establish a verified finding.</p></div>'
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
    parts.append("</div></details></section>")
    parts.append(
        section_start("sources", "Sources & credits", "Dossier evidence. Web sources remain attached to their original responses.", expanded=not app_mode) + '<div class="grid">'
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
        '</div></div></details></section>' + section_start("coverage", "Research coverage", "What was attempted, what returned, and what remains unavailable.", expanded=not app_mode) + '<div class="card scroll"><table><thead><tr><th>Topic / channel</th><th>Status</th><th>Details</th><th>Queries / sources</th></tr></thead><tbody>'
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
        '</div></details></section>' + section_start("data", "Report data", "All fields from the results JSON, preserved for inspection.", expanded=not app_mode) + '<div class="card">'
    )
    parts.append(raw_details("Explore full results JSON", payload))
    lifetime = "Saved on this computer. Reopen this report from your research shelf." if app_mode else "This local viewer expires after its configured lifetime. Saved development JSON files remain on disk."
    parts.append(
        f"</div></div></details></section><footer>Run {escape(report.id)} · Schema {escape(payload.schema_version)}<br>{lifetime}</footer></main></div></body></html>"
    )
    return "\n".join(parts)
