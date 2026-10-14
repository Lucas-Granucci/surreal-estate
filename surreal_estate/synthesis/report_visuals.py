"""Small evidence-backed report views; no inferred verdicts or invented map points."""

import json
from datetime import date
from html import escape
from math import cos, isfinite, pi


COLORS = {"schools": "#8fb3e0", "groceries": "#edcd80", "transit": "#aed6c4", "pharmacies": "#ebbcc8"}


def nearby_map(evidence, *, interactive=False):
    groups = [e for e in evidence if e.provider == "openstreetmap" and e.details.get("category") in COLORS]
    location = next((e.details for e in evidence if e.provider == "census" and "latitude" in e.details), None)
    if not groups or not location:
        return ""
    try:
        lat, lon = float(location["latitude"]), float(location["longitude"])
        if not isfinite(lat) or not isfinite(lon):
            return ""
    except (TypeError, ValueError, KeyError):
        return ""
    selected = None
    if interactive:
        selected = next((e.details["category"] for e in groups if e.details["category"] == "transit" and e.details.get("members")), None)
        selected = selected or next((e.details["category"] for e in groups if e.details.get("members")), groups[0].details["category"])
    svg = ['<svg class="mini-map" viewBox="-175 -175 350 350" role="img" aria-label="Mapped features within one kilometer of the estimated address point"><rect x="-175" y="-175" width="350" height="350" rx="22" fill="var(--bg)"/>']
    for meters in (250, 500, 750, 1000):
        radius = meters * .15
        svg.append(f'<circle r="{radius}" fill="none" stroke="var(--line)" stroke-dasharray="3 4"/><text x="4" y="{-radius + 12}">{meters} m</text>')
    # The city feed stores [latitude, longitude] pairs, not GeoJSON [lon, lat].
    # Keep the full permit geometry clipped to the same 1 km diagram.
    closure_paths = []
    for item in evidence:
        if item.provider != "wprdc_closures":
            continue
        record = item.details.get("record")
        if not isinstance(record, dict):
            continue
        try:
            geometry = record.get("geometry")
            points = json.loads(geometry) if isinstance(geometry, str) else geometry
            if not isinstance(points, list) or len(points) < 2:
                continue
            projected = []
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise ValueError("Invalid closure point")
                point_lat, point_lon = map(float, point)
                if not (-90 <= point_lat <= 90 and -180 <= point_lon <= 180):
                    raise ValueError("Invalid closure coordinates")
                x = (point_lon - lon) * cos(lat * pi / 180) * 111320 * .15
                y = -(point_lat - lat) * 110574 * .15
                projected.append(f"{x:.2f},{y:.2f}")
            description = str(record.get("work_description") or "").strip()
            closure_paths.append('<polyline class="closure-path" points="' + ' '.join(projected) + '" fill="none" stroke="var(--clay)" stroke-width="3" stroke-dasharray="2 5" stroke-linecap="round"><title>' + escape(item.title + (" · " + description if description else "")) + '</title></polyline>')
        except (ValueError, TypeError, OverflowError):
            continue
    if closure_paths:
        svg.append('<defs><clipPath id="nearby-map-clip"><circle r="150"/></clipPath></defs><g clip-path="url(#nearby-map-clip)">' + ''.join(closure_paths) + '</g>')
    svg.append('<text x="-158" y="-152">N ↑</text>')
    cards = []
    for group in groups:
        category = group.details["category"]
        rows, dots = [], []
        members = group.details.get("members", [])
        if not isinstance(members, list):
            continue
        for member in members:
            if not isinstance(member, dict):
                continue
            name = escape(str(member.get("name") or "Unnamed mapped feature"))
            distance = member.get("approximate_center_distance_m")
            distance_text = f"{distance} m" if type(distance) is int and distance >= 0 else "Distance unavailable"
            kind, identifier = member.get("object_type"), member.get("object_id")
            if kind in {"node", "way", "relation"} and type(identifier) is int and identifier > 0:
                name = f'<a href="https://www.openstreetmap.org/{kind}/{identifier}" target="_blank" rel="noopener noreferrer">{name}</a>'
            rows.append(f'<li>{name}<span>{distance_text}</span></li>')
            try:
                center = member["center"]
                x = (float(center["lon"]) - lon) * cos(lat * pi / 180) * 111320 * .15
                y = -(float(center["lat"]) - lat) * 110574 * .15
                if not isfinite(x) or not isfinite(y) or abs(x) > 170 or abs(y) > 170:
                    continue
                point_title = escape(str(member.get("name") or "Unnamed mapped feature")) if interactive else category.capitalize()
                dots.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{COLORS[category]}" stroke="var(--ink)"><title>{point_title} · {distance_text}</title></circle>')
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        svg.append(f'<g data-map-category="{category}" style="opacity:{"1" if not selected or category == selected else ".15"}">' + ''.join(dots) + '</g>')
        count = group.details.get("mapped_feature_count", len(members))
        suffix = "+" if group.details.get("count_is_lower_bound") else ""
        title = f'<i class="sw" style="background:{COLORS[category]}"></i><strong>{escape(str(count))}{suffix}</strong><span>{category.capitalize()}<small>Mapped features · within 1 km</small></span>'
        if interactive:
            title = f'<button type="button" class="cat" data-map-select="{category}" aria-pressed="{str(category == selected).lower()}">{title}</button>'
        else:
            title = f'<div class="cat">{title}</div>'
        nearby_rows = ''.join(rows[:5]) or '<li>No mapped features returned.</li>'
        more_rows = (f'<details class="more-places"><summary>Show {len(rows) - 5} more mapped places</summary><ul class="list">' + ''.join(rows[5:]) + '</ul></details>') if len(rows) > 5 else ''
        cards.append(title + f'<details data-map-list="{category}"{" open" if category == selected else ""}><summary>Explore {category}</summary><ul class="list">' + nearby_rows + '</ul>' + more_rows + '</details>')
    svg.append('<circle r="9" fill="#b5a8e0" stroke="var(--ink)" stroke-width="2"/><text x="12" y="-10">Address estimate</text></svg>')
    closure_legend = '<p class="source-meta">Dotted red lines: street-closure permit segments. Permits do not confirm active work.</p>' if closure_paths else ''
    return '<div class="card"><p class="muted">Mapped features within 1 km. Straight-line distances to points or centers, not walking times or verified businesses.</p><div class="map-wrap"><div>' + ''.join(svg) + closure_legend + '</div><div class="cats">' + ''.join(cards) + '</div></div><p class="source-meta">© OpenStreetMap contributors · ODbL. Missing map data does not establish absence. Schools are mapped locations, not attendance zones or quality ratings.</p></div>'


def closure_details(evidence):
    """Readable permit context, including saved records with unknown dates."""
    rows = []
    for item in evidence:
        record = item.details.get("record")
        if item.provider != "wprdc_closures" or not isinstance(record, dict):
            continue
        road = str(record.get("primary_street") or "Street not supplied")
        start, end = record.get("from_street"), record.get("to_street")
        segment = " to ".join(str(v) for v in (start, end) if v)
        description = str(record.get("work_description") or "No work description supplied.").strip()
        start_date = str(record['from_date'])[:10] if record.get('from_date') else 'Start date unknown'
        end_date = str(record['to_date'])[:10] if record.get('to_date') else 'End date unknown'
        dates = f"{start_date} – {end_date}"
        distance = item.details.get("approximate_segment_distance_m")
        proximity = f"About {distance} m from address estimate" if type(distance) in {int, float} else ""
        row = '<article class="closure-record"><h3>' + escape(road) + '</h3>'
        if segment:
            row += '<p class="muted">' + escape(segment) + '</p>'
        row += '<p class="work-description">' + escape(description) + '</p>'
        row += '<div class="closure-meta"><span>' + escape(dates) + '</span><span>' + escape(proximity) + '</span></div>'
        row += '<p class="source-meta">Permit ' + escape(str(record.get("permit_id") or record.get("closure_id") or "ID unavailable")) + '</p>'
        impacts = []
        for field, title in [("full_closure", "Full closure"), ("travel_lane", "Travel lane"), ("parking_lane", "Parking lane"), ("sidewalk", "Sidewalk")]:
            value = record.get(field)
            normalized = str(value).strip().lower()
            if normalized in {'true', 'yes', '1'}:
                impacts.append(title)
            elif value is not None and normalized not in {'false', 'no', '0', ''}:
                impacts.append(title + ": " + str(value))
        if impacts:
            row += '<p class="source-meta">Impacts listed: ' + escape(' · '.join(impacts)) + '</p>'
        row += '<a class="quiet-link" href="' + escape(str(item.uri), quote=True) + '" target="_blank" rel="noopener noreferrer">View permit source</a></article>'
        rows.append(row)
    if not rows:
        return ""
    html = '<p class="note">Permit descriptions explain the planned work. They do not confirm a closure is active or crews are on site.</p>' + ''.join(rows[:3])
    if len(rows) > 3:
        html += f'<details><summary>Show {len(rows) - 3} more permit records</summary>' + ''.join(rows[3:]) + '</details>'
    return html


def closure_timeline(evidence, as_of):
    rows = []
    for item in evidence:
        record = item.details.get("record")
        if not isinstance(record, dict) or "closure_id" not in record:
            continue
        try:
            start = date.fromisoformat(str(record["from_date"])[:10])
            end = date.fromisoformat(str(record["to_date"])[:10])
            if end < start:
                continue
        except (ValueError, KeyError):
            continue
        rows.append((item, start, end))
    if not rows:
        return ""
    first = min(start for _, start, _ in rows)
    last = max(end for _, _, end in rows)
    days = max(1, (last - first).days)
    html = ['<div class="card"><p class="muted">Permit dates do not confirm crews are on site. Each bar is a permit record; multiple records may describe one project.</p>', f'<div class="axis"><span>{first:%b %d, %Y}</span><span>{last:%b %d, %Y}</span></div>']
    for item, start, end in rows:
        left, width = (start - first).days / days * 100, max(0.5, (end - start).days / days * 100)
        width = min(width, 100 - left) or .5
        left = min(left, 100 - width)
        html.append(f'<p>{escape(item.title)} · {start:%b %d} – {end:%b %d}</p><div class="track" role="img" aria-label="{escape(item.title)}: {start} to {end}"><div class="bar2" style="left:{left:.2f}%;width:{width:.2f}%"></div></div>')
    html.append(f'<p class="source-meta">Report date: {as_of:%b %d, %Y}. Only the address street was searched.</p></div>')
    return ''.join(html)
