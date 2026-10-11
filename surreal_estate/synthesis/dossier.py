from surreal_estate.models import ChannelResult, Claim, RunReport


def synthesize(result: ChannelResult) -> list[Claim]:
    """Deduplicate identical observations; never infer stronger facts from summaries."""
    groups = {}
    for observation in result.observations:
        key = (
            observation.topic,
            observation.location_scope,
            observation.observed_on,
            observation.qualifier,
            observation.statement,
        )
        groups.setdefault(key, []).append(observation)
    return [
        Claim(
            statement=items[0].statement,
            observation_ids=[o.id for o in items],
            evidence_ids=list(dict.fromkeys(e for o in items for e in o.evidence_ids)),
            qualifier=items[0].qualifier,
            flags=sorted({flag for o in items for flag in o.flags}),
        )
        for items in groups.values()
    ]


def render_markdown(report: RunReport) -> str:
    lines = ["# Property research", "", report.case.address, "", f"As of {report.case.as_of}", ""]
    if report.demo:
        lines += ["**SYNTHETIC DEMO — not findings about this property or Pittsburgh.**", ""]
    if report.plan:
        lines += ["## Research plan", "", "Channels: " + ", ".join(report.plan.channels), ""]
        for query in report.plan.queries:
            lines.append(
                f"- {query.topic}: {query.geography}; {query.start_date} through {query.end_date}; "
                f"sources: {', '.join(query.source_types)}; API calls: 1; search guidance: up to {query.max_queries} queries"
            )
        lines.append("")
    lines += ["## Observations", ""]
    evidence = {e.id: e for e in report.result.evidence}
    for claim in report.claims:
        lines.append(f"- [{claim.qualifier}] {claim.statement}")
        for evidence_id in claim.evidence_ids:
            item = evidence[evidence_id]
            lines.append(f"  - Source: <{item.uri}>")
        if claim.flags:
            lines.append("  - Flags: " + ", ".join(claim.flags))
    if not report.claims:
        lines.append("No supported observations available.")
    lines += ["", "## Coverage", ""]
    for item in report.result.coverage:
        lines.append(f"- {item.channel}/{item.topic}: {item.status} — {item.reason}")
    lines += ["", "## Execution trace", ""]
    lines += [f"- {item}" for item in report.trace]
    return "\n".join(lines) + "\n"
