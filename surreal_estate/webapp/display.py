"""Lossless source transport with a small, deterministic Evidence Bench projection.

Never interpret model prose as a verified finding or infer missing provider data.
Old snapshots without area-summary fields use their original observations.
"""

from collections import defaultdict

from surreal_estate.synthesis.markdown import render_model_markdown

TOPICS = {
    "geocoding": ("Address match", "Records"),
    "property_assessment": ("Property assessment", "Records"),
    "building_permits": ("Building permits", "Records"),
    "flood_hazard": ("Flood-map context", "Records"),
    "flood_map_panels": ("Flood map panels", "Records"),
    "mapped_amenities": ("Mapped surroundings", "Surroundings"),
    "street_closures": ("Street-closure permits", "Street permits"),
    "neighborhood_discussion": ("Local discussions", "Web research"),
    "restaurant_reviews": ("Dining reviews", "Web research"),
}
CATEGORIES = {
    "transit": "Nearby transit",
    "groceries": "Grocery stores",
    "pharmacies": "Pharmacies",
    "schools": "Mapped education features",
}
GAPS = {"blocked", "error", "truncated", "not_implemented", "attempted"}


def bench_response(payload):
    data = payload.model_dump(mode="json")
    result = data["report"]["result"]
    evidence = {e["id"]: e for e in result["evidence"]}
    groups = defaultdict(list)
    for observation in result["observations"]:
        category = next(
            (
                evidence[i].get("details", {}).get("category")
                for i in observation["evidence_ids"]
                if evidence[i].get("details", {}).get("category")
            ),
            None,
        )
        groups[(observation["topic"], category)].append(observation)
    coverage = [c for c in result["coverage"] if c["reason"] != "Not selected for this run"]
    for item in coverage:
        if not any(key[0] == item["topic"] for key in groups):
            groups[(item["topic"], None)] = []
    for web in data["web"]:
        groups.setdefault((web["topic"], None), [])
    for research in result["research"]:
        groups.setdefault((research["topic"], None), [])
    rows = []
    for (topic, category), observations in groups.items():
        title, section = TOPICS.get(topic, (topic.replace("_", " ").capitalize(), "Records"))
        status = [c for c in coverage if c["topic"] == topic]
        sources = list(dict.fromkeys(i for o in observations for i in o["evidence_ids"]))
        web = [i for i, w in enumerate(data["web"]) if w["topic"] == topic]
        texts = [o["statement"] for o in observations]
        qualifier = "Public records"
        if category:
            title = CATEGORIES.get(category, title)
            qualifier = "Community-mapped · straight-line distances, not travel distances"
            detail = next(
                (
                    evidence[i]["details"]
                    for i in sources
                    if evidence[i].get("details", {}).get("category") == category
                ),
                {},
            )
            count, radius = detail.get("mapped_feature_count"), detail.get("query_radius_m")
            if isinstance(count, int) and isinstance(radius, (int, float)):
                prefix = "At least " if detail.get("count_is_lower_bound") else ""
                distance = detail.get("nearest_returned_center_distance_m")
                texts = [
                    f"{prefix}{count} mapped features within {radius / 1000:g} km."
                    + (
                        f" Closest returned point: ~{round(distance)} m."
                        if isinstance(distance, (int, float))
                        else ""
                    )
                ]
        elif any(evidence[i]["provider"] == "openstreetmap" for i in sources):
            qualifier = "Community-mapped · straight-line distances, not travel distances"
        if web:
            qualifier = "AI-assisted web research · not independently verified"
            texts = [
                "Web summary and separate AI review."
                if any(data["web"][i]["label"] == "model_assessment" for i in web)
                else "Web summary with source references."
            ]
        research = next((w for w in result["research"] if w["topic"] == topic), None)
        if research:
            sources = research["evidence_ids"]
            qualifier = "Web research · AI synthesis with source excerpts"
            texts = [f'{len(research["findings"])} source-linked findings from {len(sources)} sources.']
        if topic == "street_closures":
            qualifier = "Public records · permits do not confirm work is underway"
            if sources:
                texts = [f"{len(sources)} returned street-closure permit segments."]
        if topic.startswith("flood"):
            qualifier = "Public records · estimated street point, not a building determination"
        if any(evidence[i].get("details", {}).get("parcel_resolution", {}).get("uncertain") for i in sources):
            qualifier += " · Automatically selected parcel; uncertain match"
        if not texts:
            texts = list(dict.fromkeys(c["reason"] for c in status))
            if any(c["status"] == "error" for c in status):
                texts = [
                    "This source could not be used. Other returned research remains available."
                ]
            elif any(c["status"] == "blocked" for c in status) and topic in {
                "property_assessment",
                "building_permits",
            }:
                texts = ["A unique parcel match is needed before these records can be researched."]
        rows.append(
            {
                "id": f"finding-{len(rows)}",
                "title": title,
                "topic": topic,
                "section": section,
                "category": category,
                "statements": texts,
                "qualifier": qualifier,
                "evidence_ids": sources,
                "web_indices": web,
                "research_topic": topic if research or web else None,
                "coverage": status,
                "unresolved": any(c["status"] in GAPS for c in status)
                or any(data["web"][i]["response"]["truncated"] for i in web)
                or bool(research and any(f["assessment"] in {"conflicting", "unresolved"}
                                         for f in research["findings"])),
            }
        )

    # The approved bench groups related records; the original evidence stays intact.
    def merge(first, second, title):
        a = next((r for r in rows if r["category"] == first or r["topic"] == first), None)
        b = next((r for r in rows if r["category"] == second or r["topic"] == second), None)
        if not a or not b or a is b:
            return
        a["title"] = title
        a["statements"] = list(dict.fromkeys(a["statements"] + b["statements"]))
        a["evidence_ids"] = list(dict.fromkeys(a["evidence_ids"] + b["evidence_ids"]))
        a["coverage"] += b["coverage"]
        a["unresolved"] = a["unresolved"] or b["unresolved"]
        rows.remove(b)

    merge("groceries", "pharmacies", "Groceries & pharmacies")
    merge("property_assessment", "building_permits", "Assessment & building permits")
    merge("flood_hazard", "flood_map_panels", "Flood-map context")
    # Keep location evidence available in Sources, without dominating Findings.
    order = {"transit": 0, "groceries": 1, "pharmacies": 2, "schools": 6}
    rows.sort(
        key=lambda r: order.get(
            r["category"], 7 if r["web_indices"] else 3 if r["topic"] == "street_closures" else 4
        )
    )
    for web in data["web"]:
        web["rendered_html"] = render_model_markdown(cited_model_text(web["response"]))
    for research in result["research"]:
        for finding in research["findings"]:
            finding["ui_id"] = "web-" + finding["id"]
        if research["brief"]:
            paragraphs = [research["brief"]["overview"]] + [
                p for s in research["brief"]["sections"] for p in s["paragraphs"]
            ]
            for i, paragraph in enumerate(paragraphs):
                paragraph["ui_id"] = f'brief-{research["topic"]}-{i}'
    return {
        "version": "1.0",
        "case": data["report"]["case"],
        "demo": data["report"]["demo"],
        "findings": rows,
        "evidence": list(evidence.values()),
        "coverage": coverage,
        "web": data["web"],
        "research": result["research"],
    }


def cited_model_text(response):
    """Attach provider citations without treating answer segments as source quotes."""
    text = response["text"]
    insertions = defaultdict(set)
    for support in response["supports"]:
        segment = support["text"]
        if not segment:
            continue
        start = text.find(segment)
        if start < 0:
            continue
        for index in support["chunk_indices"]:
            if 0 <= index < len(response["chunks"]):
                uri = response["chunks"][index]["uri"]
                if uri:
                    insertions[start + len(segment)].add((index, uri))
    for end in sorted(insertions, reverse=True):
        links = " " + " ".join(f"[{i + 1}](<{uri}>)" for i, uri in sorted(insertions[end]))
        text = text[:end] + links + text[end:]
    return text
