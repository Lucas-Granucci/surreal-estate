"use strict";
// The approved prototype supplies composition and tokens, never research data.
const main = document.getElementById("main");
const dialog = document.getElementById("detail-dialog");
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const btn = (text, action, cls = "", attrs = "") =>
  `<button type="button" class="${cls}" data-action="${action}" ${attrs}>${text}</button>`;
const link = (url, title) => {
  try {
    const u = new URL(url);
    return ["http:", "https:"].includes(u.protocol)
      ? `<a class="source-link" href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>`
      : "";
  } catch {
    return "";
  }
};
const raw = (value, title = "Saved source details") =>
  `<details><summary>${esc(title)}</summary><pre class="raw">${esc(JSON.stringify(value, null, 2))}</pre></details>`;
const addressParts = (value) => {
  const parts = String(value || "").split(",");
  const street = parts.shift().trim();
  return {
    street:
      street === street.toUpperCase()
        ? street.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase())
        : street,
    locality: parts.join(",").trim(),
  };
};
const date = (value) => {
  const d = new Date(value);
  return Number.isNaN(d.valueOf())
    ? "Date not supplied"
    : d.toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
};
let draft = {};
try {
  draft = JSON.parse(sessionStorage.getItem("surreal-bench-draft") || "{}");
} catch {}
const state = {
  page: "home",
  address: typeof draft.address === "string" ? draft.address : "",
  channels: { apis: true, local: false, dining: false, ...draft.channels },
  candidates: [],
  geocoded: false,
  chosen: null,
  confirmed: false,
  webAvailable: false,
  capabilitiesLoaded: false,
  runs: [],
  job: null,
  bench: null,
  preview: null,
  query: "",
  nav: "Findings",
  filter: "Overview",
  mapCategory: "all",
  statusFilter: "All statuses",
  selected: null,
  busy: false,
  error: "",
  csrf: null,
  requestId: draft.requestId || null,
};
let timer,
  returnFocus,
  routeVersion = 0;
function save() {
  try {
    sessionStorage.setItem(
      "surreal-bench-draft",
      JSON.stringify({
        address: state.address,
        channels: state.channels,
        requestId: state.requestId,
      }),
    );
  } catch {}
}
function announce(text) {
  document.getElementById("announcement").textContent = text;
}
async function api(path, body) {
  let response;
  try {
    response = await fetch(path, {
      cache: "no-store",
      ...(body
        ? {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": state.csrf,
            },
            body: JSON.stringify(body),
          }
        : {}),
    });
  } catch {
    throw new Error(
      "Cannot reach the app. Check that it is running, then try again.",
    );
  }
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error || "The request could not finish. Please try again.",
    );
  return data;
}
async function refresh() {
  const data = await api("/api/runs");
  state.csrf = data.csrf;
  state.runs = data.runs;
  return data;
}
function running() {
  return state.runs.find((r) => r.status === "running");
}
function chosen() {
  return state.candidates.find((c) => c.confirmation === state.chosen);
}
function step(current) {
  return `<nav class="step-nav" aria-label="Research setup">${["Address", "Confirm", "Research"].map((s, i) => `${i ? '<span aria-hidden="true">/</span>' : ""}${s === current ? `<strong aria-current="step">${s}</strong>` : `<span>${s}</span>`}`).join("")}</nav>`;
}
function errorHTML() {
  return state.error
    ? `<p class="error" role="alert">${esc(state.error)}</p>`
    : "";
}
function hasChannels() {
  return (
    state.channels.apis ||
    (state.webAvailable && (state.channels.local || state.channels.dining))
  );
}
function scopeRequest() {
  return {
    address: state.address,
    geography: "Pittsburgh, Pennsylvania",
    confirmation: state.chosen,
    channels: [
      ...(state.channels.apis ? ["apis"] : []),
      ...(state.webAvailable && (state.channels.local || state.channels.dining)
        ? ["web"]
        : []),
    ],
    topics: [
      ...(state.webAvailable && state.channels.local
        ? ["neighborhood_discussion"]
        : []),
      ...(state.webAvailable && state.channels.dining
        ? ["restaurant_reviews"]
        : []),
    ],
    request_id: state.requestId,
  };
}
function home() {
  const p = state.preview,
    rows = p?.findings.filter((f) => f.topic !== "geocoding").slice(0, 3) || [],
    transit = p?.evidence.find((e) => e.details.category === "transit");
  return `<section class="hero"><h1>Know the place<br>behind the address.</h1><p class="lede">Public records, nearby places and local context. One report, with the evidence close at hand.</p><div class="hero-actions">${btn('Research an address <span aria-hidden="true">→</span>', "start", "primary")}${p ? btn("Explore saved report", "preview", "text-button") : btn("Saved reports", "saved", "text-button")}</div></section><section class="preview-wrap" aria-label="Saved report preview"><div class="preview"><div class="preview-bar"><span>${p ? esc(p.case.address) : "Your research, in one place"}</span><span>${p ? date(p.case.as_of) : "Evidence Bench"}</span></div><div class="preview-grid"><div class="preview-rail" aria-hidden="true"><span class="on">Findings</span><span>Unresolved</span><span>Sources</span><span>Research scope</span></div><div class="preview-main"><h2>The surroundings,<br>with a source.</h2>${rows.length ? rows.map((f) => `<div class="preview-finding"><b>${esc(f.title)}</b><p>${esc(f.statements[0])}</p></div>`).join("") : '<p class="preview-empty">Research an address to see its records, surroundings and available evidence here.</p>'}</div><div class="preview-evidence"><div class="eyebrow">${transit ? "OpenStreetMap" : "Evidence"}</div><h3>${transit ? "Closest returned transit features" : "Keep the source close."}</h3>${transit ? distances(transit) : '<p class="caption">Select a finding to inspect its source and understand what it can tell you.</p>'}</div></div></div></section><section class="value-section" aria-label="About SurrealEstate"><div class="value-line"><h2>Find what matters.</h2><p>Move between surroundings, public records and local accounts without losing the context of the address.</p></div><div class="value-line"><h2>Follow the evidence.</h2><p>Inspect the source behind a finding, including what it can—and cannot—tell you.</p></div><details class="coverage"><summary>Where does SurrealEstate have coverage?</summary><p>Property and permit coverage focuses on Pittsburgh. Mapped places and other sources vary by location. Unavailable research is identified in your report.</p></details></section>`;
}
function distances(e) {
  const members = (e.details.members || [])
    .filter((m) => Number.isFinite(m.approximate_center_distance_m))
    .slice()
    .sort(
      (a, b) =>
        a.approximate_center_distance_m - b.approximate_center_distance_m,
    )
    .slice(0, 3);
  const max = Math.max(
    ...members.map((m) => m.approximate_center_distance_m),
    1,
  );
  return (
    members
      .map(
        (m) =>
          `<div class="distance"><span><span>${esc(m.name || "Unnamed mapped feature")}</span><span>~${Math.round(m.approximate_center_distance_m)} m</span></span><i style="width:${Math.max(1, (m.approximate_center_distance_m / max) * 100)}%"></i></div>`,
      )
      .join("") +
    '<p class="caption">Straight-line distances to mapped points, not travel distances.</p>'
  );
}
function entry() {
  return `<section class="setup">${step("Address")}<h1>Where would you like<br>to look?</h1><form id="address-form"><label for="address" class="field-label">Address</label><input type="text" id="address" name="address" value="${esc(state.address)}" placeholder="Street address, city or postcode" autocomplete="street-address" minlength="5" maxlength="200" required aria-describedby="address-error" ${state.busy ? "disabled" : ""}><div id="address-error">${errorHTML()}</div>${btn("Use 414 Grant Street, Pittsburgh", "fill-example", "text-button example-button")}<div class="actions"><button type="submit" class="primary" ${state.busy ? "disabled" : ""}>${state.busy ? "Finding address…" : 'Find address <span aria-hidden="true">→</span>'}</button>${btn("Back", "home", "text-button")}</div></form></section>`;
}
function confirm() {
  return `<section class="setup">${step("Confirm")}<h1>Is this the right place?</h1>${state.candidates.length ? `<fieldset><legend class="sr-only">Choose the matching address</legend>${state.candidates.map((c) => `<label class="candidate"><input type="radio" name="candidate" value="${esc(c.confirmation)}" ${state.chosen === c.confirmation ? "checked" : ""}><span><strong>${esc(addressParts(c.address).street)}</strong><span>${esc(addressParts(c.address).locality)}</span><span>US Census address match</span></span></label>`).join("")}</fieldset><details class="location-detail"><summary>About this location match</summary><p>Census places this address along a street range. It is an estimated street point, not a building entrance or parcel boundary.</p>${chosen() ? `<p>${esc(chosen().latitude)}, ${esc(chosen().longitude)}</p>` : ""}</details>` : '<p class="empty-state">No matching address found. Check the street number, city, state or ZIP code.</p>'}${errorHTML()}<div class="actions">${btn("Confirm location", "confirm", "primary", state.chosen ? "" : "disabled")}${btn("Edit address", "edit-address", "text-button")}</div></section>`;
}
function channels() {
  return `<section class="setup">${step("Research")}<h1>What should we research?</h1><div class="address-context"><span>${esc(chosen()?.address || state.address)}</span>${btn("Edit", "edit-address", "text-button small-button", state.busy ? "disabled" : "")}</div><label class="channel"><input type="checkbox" name="apis" ${state.channels.apis ? "checked" : ""} ${state.busy ? "disabled" : ""}><span><strong>Public records & nearby places</strong><p>Property and permit records, mapped surroundings and flood-map context.</p></span></label><p class="group-label">Optional web research</p>${!state.capabilitiesLoaded ? '<p class="muted" role="status">Checking availability…</p>' : !state.webAvailable ? `<p class="error" role="status">Web research is unavailable for this session.</p>${btn("Check again", "capabilities", "text-button small-button")}` : ""}${[
    [
      "local",
      "Local discussions",
      "Accounts and perspectives from local discussions.",
    ],
    [
      "dining",
      "Dining research",
      "Nearby restaurants and themes from reviews.",
    ],
  ]
    .map(
      ([k, t, d]) =>
        `<label class="channel"><input type="checkbox" name="${k}" ${state.channels[k] ? "checked" : ""} ${!state.webAvailable || state.busy ? "disabled" : ""}><span><strong>${t}</strong><p>${d}</p></span></label>`,
    )
    .join(
      "",
    )}<details class="location-detail"><summary>How web research works</summary><p>AI summarizes web sources and provides a separate review of its claims. Opinions and model assessments remain distinct from public records.</p></details>${errorHTML()}<div class="actions">${btn(state.busy ? "Starting research…" : "Generate report", "generate", "primary", hasChannels() && !state.busy ? "" : "disabled")}${btn("Back", "back-confirm", "text-button", state.busy ? "disabled" : "")}</div></section>`;
}
function progress() {
  const j = state.job;
  return `<section class="setup"><div class="eyebrow">${!j ? "Loading research" : j.status === "running" ? "Research in progress" : j.status === "failed" ? "Research interrupted" : "Report ready"}</div><h1>${esc(addressParts(j?.address || "Your research").street)}</h1><p class="lede">${esc(j?.geography || "")}</p><div class="status-list" aria-live="polite">${(j?.progress?.steps || []).map((s) => `<div class="status-row"><span class="status-mark ${s.state === "done" ? "done" : ""}" aria-hidden="true">${s.state === "done" ? "✓" : s.state === "active" ? '<span class="spinner"></span>' : s.state === "waiting" ? "○" : "—"}</span><span>${esc(s.label)}</span><small>${esc({ done: "Finished", active: "In progress", waiting: "Waiting", stopped: "Stopped", skipped: "Not run" }[s.state] || s.state)}</small></div>`).join("")}</div><p class="status-message">${esc(j?.status === "running" ? j.progress?.detail || j.message : j?.message || "Loading…")}</p>${errorHTML()}<div class="actions">${j?.status === "complete" ? btn("Explore report", "open", "primary", `data-id="${j.id}"`) : ""}${j?.status === "failed" ? btn("Try again", "retry", "primary") : ""}${state.error ? btn("Reconnect", "reconnect", "secondary") : ""}${btn("Saved reports", "saved", "text-button")}</div></section>`;
}
function metadata(e) {
  return `<dl class="meta">${[
    ["Retrieved", e.retrieved_at],
    ["Source updated", e.source_updated_at],
    ["Record date", e.record_date],
    ["Matching method", e.match_method?.replaceAll("_", " ")],
    ["Attribution", e.attribution],
  ]
    .filter(([, v]) => v)
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`)
    .join("")}</dl>`;
}
function memberDetails(m) {
  return `<div class="record"><strong>${esc(m.name || "Unnamed mapped feature")}</strong>${Number.isFinite(m.approximate_center_distance_m) ? `<p>~${Math.round(m.approximate_center_distance_m)} m straight-line</p>` : ""}${link(m.uri, "Open mapped feature")}</div>`;
}
function sourceDetails(e) {
  const members = e.details.members || [],
    record = e.details.record;
  return `<div class="evidence-section"><h3>${esc(e.title)}</h3><p>${esc(e.excerpt)}</p>${
    record
      ? `<div class="record">${[
          ["Street", record.primary_street],
          ["From", record.from_street],
          ["To", record.to_street],
          ["Work described", record.work_description],
          ["Start", record.from_date],
          ["End", record.to_date],
        ]
          .filter(([, v]) => v)
          .map(([k, v]) => `<p><strong>${k}</strong><br>${esc(v)}</p>`)
          .join("")}</div>`
      : ""
  }${members.slice(0, 3).map(memberDetails).join("")}${members.length > 3 ? `<details><summary>${members.length - 3} more mapped features</summary>${members.slice(3).map(memberDetails).join("")}</details>` : ""}${e.details.count_is_lower_bound ? '<p class="caption">The category was capped; this count is a lower bound.</p>' : ""}${link(e.uri, "Open source")}<details><summary>Source & retrieval</summary>${metadata(e)}${e.provider === "openstreetmap" ? link("https://www.openstreetmap.org/copyright", "© OpenStreetMap contributors · ODbL") : ""}</details>${raw(e.details)}</div>`;
}

function webDetails(w) {
  const r = w.response;
  return `<div class="evidence-section"><h3>${w.label === "model_assessment" ? "AI review" : "Web summary"}</h3><p class="caption">Model-reported · not independently verified${r.truncated ? " · Response incomplete" : ""}</p><details><summary>Read ${w.label === "model_assessment" ? "the AI review" : "the summary"}</summary><div class="web-prose">${w.rendered_html}</div></details>${r.search_entry_point ? `<p class="caption">Google Search Suggestions</p><iframe class="suggestions" title="Google Search Suggestions" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" srcdoc="${esc(r.search_entry_point)}"></iframe>` : ""}<details><summary>Sources and supporting passages</summary>${r.chunks.map((c, i) => `<div class="record"><strong>Source ${i + 1}</strong>${link(c.uri, c.title || "Open source") || "<p>Source URL not supplied</p>"}</div>`).join("")}${r.supports.map((s) => `<div class="record"><p>${esc(s.text)}</p><p class="caption">Sources: ${s.chunk_indices.map((i) => i + 1).join(", ") || "Not supplied"}</p></div>`).join("")}${raw(r, "Full saved response")}</details></div>`;
}
function evidence(id) {
  const b = state.bench;
  if (!id || !b)
    return '<div class="empty-inspector"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 3h16v18H4zM8 8h8M8 12h8M8 16h5"/></svg><p>Select a finding<br>to inspect its evidence.</p></div>';
  const f = id.startsWith("overview-")
      ? overviewFinding(id.slice(9))
      : b.findings.find((f) => f.id === id),
    e = b.evidence.find((e) => e.id === id);
  if (!f && !e) return evidence(null);
  return `<div class="evidence-head"><div class="eyebrow">${esc(f?.qualifier.split(" · ")[0] || e.kind.replaceAll("_", " "))}</div>${btn("×", "close-evidence", "icon-button", 'aria-label="Close evidence"')}</div><h2 tabindex="-1" class="evidence-title">${esc(f?.title || e.title)}</h2>${
    e
      ? sourceDetails(e)
      : f.evidence_ids
          .map((id) => sourceDetails(b.evidence.find((e) => e.id === id)))
          .join("") +
        f.web_indices.map((i) => webDetails(b.web[i])).join("") +
        f.coverage
          .filter((c) => c.status !== "complete")
          .map(
            (c) =>
              `<div class="evidence-section"><h3>${esc(c.status === "empty" ? "No records returned" : c.status.replaceAll("_", " "))}</h3><p>${esc(c.reason)}</p>${c.parcel_candidates?.length ? c.parcel_candidates.map((p) => `<div class="record"><strong>${esc(p.parcel_id)}</strong><p>${esc(p.address)}</p><p>${esc(p.property_use)}</p>${link(p.source_url, "Open parcel source")}</div>`).join("") : ""}${raw(c, "Coverage details")}</div>`,
          )
          .join("")
  }${f && !f.evidence_ids.length && !f.web_indices.length && !f.coverage.length ? "<p>No supporting source was retained.</p>" : ""}`;
}
function findings() {
  return state.bench?.findings.filter((f) => f.topic !== "geocoding") || [];
}
function sources() {
  return (
    state.bench.evidence
      .map(
        (e) =>
          `<div class="source-row"><div><h3>${esc(e.title)}</h3><p>${esc(e.provider)} · ${esc(e.kind.replaceAll("_", " "))}</p></div>${btn("Inspect", "evidence", "secondary", `data-id="${esc(e.id)}"`)}</div>`,
      )
      .join("") +
      state.bench.findings
        .filter((f) => f.web_indices.length)
        .map(
          (f) =>
            `<div class="source-row"><div><h3>${esc(f.title)}</h3><p>Web sources · summary and AI review</p></div>${btn("Inspect", "evidence", "secondary", `data-id="${f.id}"`)}</div>`,
        )
        .join("") || '<p class="empty-state">No sources were returned.</p>'
  );
}
function scope() {
  const b = state.bench;
  return `<dl class="scope-list"><div><dt>Address</dt><dd>${esc(b.case.address)}</dd></div><div><dt>Report date</dt><dd>${date(b.case.as_of)}</dd></div><div><dt>Research</dt><dd>${[...new Set(b.findings.map((f) => f.section))].map(esc).join("<br>")}</dd></div></dl><details class="location-detail"><summary>Search boundaries</summary><p>Mapped-place distances are straight-line measurements to points or feature centres. Census locations are estimated street points, not verified entrances or parcel boundaries.</p></details><details class="location-detail"><summary>Coverage and missing data</summary>${b.coverage.map((c) => `<div class="record"><strong>${esc(c.topic.replaceAll("_", " "))} · ${esc(c.status.replaceAll("_", " "))}</strong><p>${esc(c.reason)}</p></div>`).join("")}</details><div class="actions">${btn("Export source JSON", "export", "secondary")}${btn("Research again", "research-again", "text-button")}</div>`;
}
const mapCategoryStyles = [
  { id: "transit", label: "Transit", shape: "circle", color: "#55769A" },
  { id: "groceries", label: "Groceries", shape: "square", color: "#95634A" },
  { id: "schools", label: "Education", shape: "diamond", color: "#777093" },
  { id: "pharmacies", label: "Pharmacies", shape: "cross", color: "#56816B" },
];
function validCoordinates(lat, lon) {
  return (
    Number.isFinite(lat) &&
    Math.abs(lat) <= 90 &&
    Number.isFinite(lon) &&
    Math.abs(lon) <= 180
  );
}
function distanceLabel(meters) {
  return meters >= 1000
    ? `${Number((meters / 1000).toFixed(2))} km`
    : `${Math.round(meters)} m`;
}
function mappedCategories() {
  return mapCategoryStyles.flatMap((c) => {
    const source = state.bench.evidence.find(
      (e) =>
        e.provider === "openstreetmap" &&
        e.details?.category === c.id &&
        Array.isArray(e.details.members),
    );
    return source ? [{ ...c, details: source.details }] : [];
  });
}
function overviewFinding(topic) {
  const rows = state.bench.findings.filter(
    (f) => f.topic === topic || f.coverage.some((c) => c.topic === topic),
  );
  if (!rows.length) return null;
  return {
    ...rows[0],
    evidence_ids: [...new Set(rows.flatMap((f) => f.evidence_ids))],
    web_indices: [...new Set(rows.flatMap((f) => f.web_indices))],
    coverage: rows.flatMap((f) => f.coverage),
  };
}
function overviewRows() {
  const b = state.bench;
  const topics = [
    ...new Set([
      ...b.coverage.map((c) => c.topic),
      ...b.findings.map((f) => f.topic),
    ]),
  ];
  const titles = {
    geocoding: "Address match",
    property_assessment: "Property assessment",
    building_permits: "Building permits",
    flood_hazard: "Flood-map context",
    flood_map_panels: "Flood map panels",
    mapped_amenities: "Mapped surroundings",
    street_closures: "Street-closure permits",
    neighborhood_discussion: "Local discussions",
    restaurant_reviews: "Dining research",
  };
  return topics.map((topic) => {
    const coverage = b.coverage.filter((c) => c.topic === topic);
    const finding = b.findings.find(
      (f) => f.topic === topic || f.coverage.some((c) => c.topic === topic),
    );
    const statuses = coverage.map((c) => c.status);
    const limited =
      (finding?.web_indices || []).some((i) => b.web[i].response.truncated) ||
      (topic === "mapped_amenities" &&
        mappedCategories().some((c) => c.details.count_is_lower_bound));
    const status =
      statuses.includes("error") || statuses.includes("failed")
        ? "Failed"
        : statuses.includes("blocked")
          ? "Blocked"
          : statuses.includes("truncated") || limited
            ? "Limited"
            : statuses.some((s) =>
                  ["unavailable", "not_implemented", "attempted"].includes(s),
                )
              ? "Unavailable"
              : statuses.length &&
                  statuses.every((s) => ["complete", "empty"].includes(s))
                ? "Complete"
                : "Unknown";
    const outcome =
      [
        ...new Set(
          coverage
            .map((c) =>
              c.status === "empty" ? `No records found. ${c.reason}` : c.reason,
            )
            .filter(Boolean),
        ),
      ].join(" ") ||
      finding?.statements.join(" ") ||
      "No research outcome was retained.";
    return {
      title: esc(titles[topic] || finding?.title || topic.replaceAll("_", " ")),
      outcome: esc(outcome),
      id: finding ? `overview-${topic}` : null,
      status,
    };
  });
}
function spatialOverview() {
  const mapCategories = mappedCategories();
  const origin = state.bench.evidence
    .map((e) => e.details)
    .find((d) => validCoordinates(d?.latitude, d?.longitude));
  if (!origin || !mapCategories.length)
    return '<div class="map-unavailable">Saved coordinates are unavailable for this report. Retained findings and sources remain available below.</div>';
  const radius = Math.max(
    ...mapCategories
      .map((c) => c.details.query_radius_m)
      .filter((v) => Number.isFinite(v) && v > 0),
    ...mapCategories.flatMap((c) =>
      c.details.members
        .filter((m) => validCoordinates(m.center?.lat, m.center?.lon))
        .map((m) =>
          Math.hypot(
            (m.center.lon - origin.longitude) *
              111320 *
              Math.cos((origin.latitude * Math.PI) / 180),
            (m.center.lat - origin.latitude) * 111320,
          ),
        ),
    ),
    1,
  );
  const scale = 218 / radius;
  const selected = state.mapCategory || "all";
  const project = (c) => [
    260 +
      (c.lon - origin.longitude) *
        111320 *
        Math.cos((origin.latitude * Math.PI) / 180) *
        scale,
    260 - (c.lat - origin.latitude) * 111320 * scale,
  ];
  const groups = mapCategories.filter(
    (c) => selected === "all" || c.id === selected,
  );
  const markers = groups
    .map((c) =>
      c.details.members
        .map((m) => {
          if (!validCoordinates(m.center?.lat, m.center?.lon)) return "";
          const [x, y] = project(m.center),
            attrs = `fill="${c.color}" stroke="var(--surface)" stroke-width="1.5"`;
          const shape =
            c.shape === "circle"
              ? `<circle cx="${x}" cy="${y}" r="4.5" ${attrs}/>`
              : c.shape === "square"
                ? `<rect x="${x - 4.5}" y="${y - 4.5}" width="9" height="9" rx="1" ${attrs}/>`
                : c.shape === "diamond"
                  ? `<path d="M${x},${y - 6}l6,6 -6,6 -6,-6z" ${attrs}/>`
                  : `<path d="M${x - 5},${y}h10M${x},${y - 5}v10" stroke="${c.color}" stroke-width="3"/>`;
          return `<g><title>${esc(m.name || "Unnamed feature")} · ${Number.isFinite(m.approximate_center_distance_m) ? "~" + Math.round(m.approximate_center_distance_m) + " m" : "Distance unavailable"}</title>${shape}</g>`;
        })
        .join(""),
    )
    .join("");
  return `<div class="spatial-card"><div class="spatial-plot"><svg viewBox="0 0 520 520" role="img" aria-labelledby="map-title map-description"><title id="map-title">Mapped places around ${esc(state.bench.case.address)}</title><desc id="map-description">North-up coordinate plot of saved OpenStreetMap feature centres, with a distance reference circle around the estimated address point. Category totals and an accessible location list follow.</desc><defs><clipPath id="mapclip"><rect x="12" y="12" width="496" height="496" rx="4"/></clipPath></defs><g class="map-grid" fill="none" stroke="#DADAE0" stroke-width="0.6">${[60, 160, 260, 360, 460].map((v) => `<path d="M${v} 0V520M0 ${v}H520"/>`).join("")}</g><circle cx="260" cy="260" r="218" fill="none" stroke="#858591" stroke-width="1.3" stroke-dasharray="5 6" class="search-radius"/><g clip-path="url(#mapclip)">${markers}</g><circle cx="260" cy="260" r="12" fill="#FFFFFF" stroke="#303038" stroke-width="2" class="address-ring"/><circle cx="260" cy="260" r="4" fill="#303038" class="address-dot"/><text x="390" y="76" fill="#60606B" font-size="12" class="map-label">${esc(distanceLabel(radius))}</text><path d="M487 47V23m-4 6 4-6 4 6" fill="none" stroke="#858591" class="north-arrow"/><text x="482" y="64" fill="#60606B" font-size="12" class="map-label">N</text><path d="M26 489h109m-109-4v8m109-8v8" fill="none" stroke="#858591" class="scale-line"/><text x="27" y="476" fill="#60606B" font-size="12" class="map-label">${esc(distanceLabel(radius / 2))}</text></svg></div><div class="map-legend">${mapCategories
    .map((c) => {
      const d = c.details;
      return btn(
        `<span class="legend-inner"><span class="legend-symbol ${c.shape}" style="--marker:${c.color}" aria-hidden="true"></span><strong>${d.count_is_lower_bound ? "≥" : ""}${esc(d.mapped_feature_count ?? d.members.length)}</strong><span>${c.label}</span></span>`,
        "map-category",
        "legend-row",
        `data-category="${c.id}" aria-pressed="${selected === c.id}" aria-label="Show ${c.label.toLowerCase()} on map"`,
      );
    })
    .join(
      "",
    )}${selected !== "all" ? btn("Show all places", "map-category", "text-button map-reset", 'data-category="all"') : ""}</div></div><p class="map-caption">Saved feature centres · estimated address point · north up. © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a></p><details class="location-detail place-list"><summary>View mapped locations</summary><div class="table-scroll"><table class="overview-table"><thead><tr><th>Place</th><th>Category</th><th>Distance</th></tr></thead><tbody>${groups.flatMap((c) => c.details.members.map((m) => `<tr><td>${link(m.uri, m.name || "Unnamed mapped feature") || esc(m.name || "Unnamed mapped feature")}</td><td>${c.label}</td><td>${Number.isFinite(m.approximate_center_distance_m) ? "~" + Math.round(m.approximate_center_distance_m) + " m" : "Distance unavailable"}</td></tr>`)).join("")}</tbody></table></div><p>Distances are straight-line measurements to mapped points or centres, not travel distances. Counts describe retained mapped features, not necessarily distinct facilities. Capped categories are lower bounds. Features without saved coordinates appear only in the list. The dashed circle is a distance reference, not a property boundary.</p></details>`;
}
function overview() {
  const rows = overviewRows();
  const shown = rows.filter(
    (r) =>
      !state.statusFilter ||
      state.statusFilter === "All statuses" ||
      r.status === state.statusFilter,
  );
  return `<section class="overview-section" aria-label="Location overview"><h2>Location overview</h2><div id="spatial-overview">${spatialOverview()}</div></section><section class="overview-section" aria-label="Research overview"><div class="overview-heading"><h2>Research overview</h2><label><span class="sr-only">Filter research status</span><select id="status-filter">${["All statuses", "Complete", "Blocked", "Limited", "Failed", "Unavailable", "Unknown"].map((v) => `<option ${v === (state.statusFilter || "All statuses") ? "selected" : ""}>${v}</option>`).join("")}</select></label></div><div class="table-scroll research-table" tabindex="0" role="region" aria-label="Research status table"><table class="overview-table"><thead><tr><th>Research</th><th>Outcome</th><th>Status</th></tr></thead><tbody>${shown.length ? shown.map((r) => `<tr><th scope="row">${!r.id ? r.title : btn(r.title, "evidence", "table-topic", `data-id="${r.id}"`)}</th><td>${r.outcome}</td><td><span class="status-label status-${r.status.toLowerCase().replace(" ", "-")}">${r.status}</span></td></tr>`).join("") : `<tr><td colspan="3" class="empty-status">No ${esc((state.statusFilter || "").toLowerCase())} research recorded in this report.</td></tr>`}</tbody></table></div><ul class="mobile-status-list" aria-label="Research status">${shown.length ? shown.map((r) => `<li><div class="mobile-status-heading">${!r.id ? `<strong>${r.title}</strong>` : btn(r.title, "evidence", "mobile-topic", `data-id="${r.id}"`)}<span class="status-label status-${r.status.toLowerCase().replace(" ", "-")}">${r.status}</span></div><p>${r.outcome}</p></li>`).join("") : `<li>No ${esc((state.statusFilter || "").toLowerCase())} research recorded in this report.</li>`}</ul><details class="location-detail"><summary>What these statuses mean</summary><p>Complete means the research finished, not that its claims are independently verified. Limited indicates capped results; blocked research needs missing information. Failed is a research error, while unavailable means a source could not be used. Unknown means no completion status was retained. A successful search with no matches is shown as complete with “No records found” in its outcome.</p></details></section>`;
}
function report() {
  const b = state.bench;
  if (!b)
    return `<section class="setup"><h1>Opening report…</h1>${errorHTML()}${btn("Saved reports", "saved", "text-button")}</section>`;
  const fs = findings(),
    gaps = fs.filter((f) => f.unresolved),
    topics = [
      "Overview",
      "All topics",
      ...["Surroundings", "Records", "Street permits", "Local accounts"].filter(
        (t) => fs.some((f) => f.section === t),
      ),
    ];
  if (!topics.includes(state.filter)) state.filter = "Overview";
  const rows = fs.filter(
    (f) =>
      (state.nav !== "Unresolved" || f.unresolved) &&
      (state.nav !== "Findings" ||
        state.filter === "All topics" ||
        f.section === state.filter),
  );
  return `<div class="report-shell"><nav class="report-rail" aria-label="Report">${["Findings", "Unresolved", "Sources", "Research scope"].map((n) => btn(n, "report-nav", "", `data-nav="${n}" ${state.nav === n ? 'aria-current="page"' : ""}`)).join("")}<div class="export">${btn('Export JSON <span aria-hidden="true">↗</span>', "export")}</div></nav><section class="report-work"><header class="report-heading"><h1>${esc(addressParts(b.case.address).street)}</h1><p>${esc(addressParts(b.case.address).locality || b.case.geography)} · Report dated ${date(b.case.as_of)}${b.demo ? " · Synthetic demo" : ""}</p></header>${errorHTML()}${state.nav === "Findings" ? `${gaps.length ? `<div class="notice"><span>${gaps.length === 1 ? `${esc(gaps[0].title)} needs attention.` : `${gaps.length} research topics are unresolved.`}</span>${btn("Review", "review-gap")}</div>` : ""}<div class="filters" aria-label="Filter findings">${topics.map((t) => btn(t, "filter", "", `data-filter="${t}" aria-pressed="${state.filter === t}"`)).join("")}</div>` : `<h2 class="panel-title" tabindex="-1">${state.nav}</h2>`}${
    state.nav === "Sources"
      ? sources()
      : state.nav === "Research scope"
        ? scope()
        : state.nav === "Findings" && state.filter === "Overview"
          ? overview()
          : rows.length
            ? rows
                .map(
                  (f) =>
                    `<article class="finding ${state.selected === f.id ? "selected" : ""}" id="${f.id}"><div><h2>${esc(f.title)}</h2><p>${esc(f.statements[0] || "No finding returned.")}</p>${
                      f.statements.length > 1
                        ? `<details><summary>${f.statements.length - 1} more ${f.topic === "street_closures" ? "records" : "findings"}</summary>${f.statements
                            .slice(1)
                            .map((t) => `<p>${esc(t)}</p>`)
                            .join("")}</details>`
                        : ""
                    }<p class="qualifier">${esc(f.qualifier)}</p></div>${btn("Evidence", "evidence", "", `data-id="${f.id}" aria-label="Inspect evidence for ${esc(f.title)}"`)}</article>`,
                )
                .join("")
            : `<p class="empty-state">${state.nav === "Unresolved" ? "No unresolved topics were recorded." : "No findings were returned for this topic."}</p>`
  }</section><aside class="report-inspector" id="inspector" aria-label="Evidence inspector">${evidence(state.selected)}</aside></div>`;
}
function savedResults() {
  const runs = state.runs.filter((r) =>
    r.address.toLowerCase().includes(state.query.trim().toLowerCase()),
  );
  return runs.length
    ? runs
        .map(
          (r) =>
            `<article class="saved-row"><div><h2>${esc(r.address)}</h2><p>${esc(r.geography || "")} · ${date(r.created_at)}</p><p>${r.demo ? "Synthetic demo · " : ""}${r.status === "complete" ? (r.partial ? "Some topics unresolved" : "Report ready") : r.status === "failed" ? "Research interrupted" : "Research in progress"}</p></div>${btn(r.status === "complete" ? 'Open report <span aria-hidden="true">→</span>' : "View progress", r.status === "complete" ? "open" : "watch", "secondary", `data-id="${r.id}"`)}</article>`,
        )
        .join("")
    : `<p class="empty-state">${state.query ? `No saved reports match “${esc(state.query)}”.` : "Your saved reports will appear here."}</p>${state.query ? btn("Clear search", "clear-search", "text-button") : ""}`;
}
function saved() {
  return `<section class="saved-page"><div class="saved-heading"><h1>Saved reports</h1>${btn('New research <span aria-hidden="true">↗</span>', "new", "primary")}</div>${errorHTML()}<label for="saved-search" class="sr-only">Search saved reports</label><div class="saved-search"><input type="search" id="saved-search" value="${esc(state.query)}" placeholder="Search by address"></div><div id="saved-results">${savedResults()}</div></section>`;
}
function render(focus = false) {
  main.innerHTML = `<div class="fade-in">${({ home, entry, confirm, channels, progress, report, saved }[state.page] || home)()}</div>`;
  const top = document.querySelector(".app-header nav .secondary");
  top.dataset.action = running() ? "resume-progress" : "new";
  top.innerHTML = running()
    ? "View progress"
    : 'New research <span aria-hidden="true">↗</span>';
  document.title =
    (state.page === "report" && state.bench
      ? state.bench.case.address
      : state.page === "saved"
        ? "Saved reports"
        : "Know the place") + " · SurrealEstate";
  if (focus) {
    const heading = main.querySelector("h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
    window.scrollTo(0, 0);
  }
}
function go(page) {
  closeDialog(false);
  state.error = "";
  location.hash = page === "home" ? "home" : page;
}
async function checkCapabilities() {
  try {
    const c = await api("/api/capabilities");
    state.webAvailable = c.web.available;
  } catch {
    state.webAvailable = false;
  }
  state.capabilitiesLoaded = true;
  if (state.page === "channels") render();
}
async function route() {
  const version = ++routeVersion;
  clearTimeout(timer);
  state.error = "";
  closeDialog(false);
  const path =
    location.hash.slice(1) ||
    ((location.pathname.match(/^\/reports\/([\w-]+)\/dashboard$/) || [])[1]
      ? `report/${location.pathname.split("/")[2]}`
      : "home");
  const [page, id] = path.split("/");
  state.page = [
    "home",
    "entry",
    "confirm",
    "channels",
    "progress",
    "report",
    "saved",
  ].includes(page)
    ? page
    : "home";
  if (["confirm", "channels"].includes(state.page) && !state.geocoded)
    state.page = "entry";
  if (state.page === "channels" && !state.confirmed) state.page = "confirm";
  if (page === "report") {
    state.bench = null;
    state.mapCategory = "all";
    state.statusFilter = "All statuses";
    state.selected = null;
    state.nav = "Findings";
    state.filter = "Overview";
  }
  if (page === "progress" && state.job?.id !== id) state.job = null;
  render(true);
  try {
    if (page === "report" && id) {
      const b = await api(`/reports/${encodeURIComponent(id)}/bench.json`);
      if (version !== routeVersion) return;
      state.bench = b;
      state.reportId = id;
      state.selected =
        b.findings.find((f) => f.category === "transit")?.id ||
        b.findings.find((f) => f.topic !== "geocoding")?.id ||
        null;
      render(true);
    } else if (page === "progress" && id) {
      await poll(id, version);
    } else if (page === "saved") {
      await refresh();
      if (version === routeVersion) render();
    } else if (page === "home" && !state.preview) {
      await loadPreview(version);
    } else if (page === "channels") {
      checkCapabilities();
    }
  } catch (e) {
    if (version === routeVersion) {
      state.error = e.message;
      render();
    }
  }
}
async function loadPreview(version) {
  const r = state.runs.find((r) => r.status === "complete" && !r.demo);
  if (!r) return;
  try {
    state.preview = await api(`/reports/${r.id}/bench.json`);
    state.previewId = r.id;
    if (version === routeVersion && state.page === "home") render();
  } catch {
    /* The empty preview is valid when an old snapshot is unavailable. */
  }
}
async function locate() {
  if (state.busy) return;
  state.address = document.getElementById("address").value.trim();
  state.busy = true;
  state.error = "";
  save();
  render();
  try {
    await refresh();
    const data = await api("/api/geocode", {
      address: state.address,
      geography: "Pittsburgh, Pennsylvania",
    });
    state.candidates = data.candidates;
    state.geocoded = true;
    state.chosen = null;
    state.confirmed = false;
    state.requestId = null;
    save();
    go("confirm");
  } catch (e) {
    state.error = e.message;
  } finally {
    state.busy = false;
    render();
  }
}
async function generate() {
  if (state.busy || !state.confirmed || !hasChannels()) return;
  state.busy = true;
  state.error = "";
  state.requestId ||= crypto.randomUUID();
  save();
  render();
  try {
    await refresh();
    const j = await api("/api/runs", scopeRequest());
    state.job = j;
    state.runs = [j, ...state.runs.filter((r) => r.id !== j.id)];
    go(`progress/${j.id}`);
  } catch (e) {
    state.error = e.message;
  } finally {
    state.busy = false;
    render();
  }
}
async function poll(id, version) {
  try {
    const j = await api(`/api/runs/${encodeURIComponent(id)}`);
    if (version !== routeVersion) return;
    state.job = j;
    state.runs = [j, ...state.runs.filter((r) => r.id !== j.id)];
    state.error = "";
    render();
    if (j.status === "running")
      timer = setTimeout(() => poll(id, version), 1500);
    else announce(j.message);
  } catch (e) {
    if (version !== routeVersion) return;
    state.error = e.message;
    render();
    timer = setTimeout(() => poll(id, version), 4000);
  }
}
function openDialog(title, body, cls = "") {
  returnFocus = document.activeElement;
  dialog.className = cls;
  document.getElementById("dialog-body").innerHTML =
    `<div class="dialog-content"><div class="dialog-top"><h2 id="dialog-title" tabindex="-1">${esc(title)}</h2>${btn("×", "close-dialog", "icon-button", 'aria-label="Close dialog"')}</div>${body}</div>`;
  dialog.showModal();
  dialog.querySelector("h2").focus();
}
function closeDialog(restore = true) {
  if (dialog.open) {
    dialog.close();
    if (restore && returnFocus?.isConnected)
      returnFocus.focus({ preventScroll: true });
  }
}
function openEvidence(id, trigger) {
  state.selected = id;
  document
    .querySelectorAll(".finding")
    .forEach((e) => e.classList.toggle("selected", e.id === id));
  const pane = document.getElementById("inspector");
  if (pane) {
    pane.innerHTML = evidence(id);
    pane.scrollTop = 0;
  }
  if (matchMedia("(max-width:1120px)").matches) {
    const title =
      state.bench.findings.find((f) => f.id === id)?.title ||
      state.bench.evidence.find((e) => e.id === id)?.title ||
      "Evidence";
    openDialog(
      title,
      `<div class="report-inspector">${evidence(id)}</div>`,
      "evidence-dialog",
    );
  } else {
    returnFocus = trigger;
    pane?.querySelector(".evidence-title")?.focus({ preventScroll: true });
  }
}
function newSearch() {
  if (running()) {
    go(`progress/${running().id}`);
    return;
  }
  if (state.address)
    openDialog(
      "Start another search?",
      '<p>Your current address and research choices will be cleared. Saved reports remain available.</p><div class="actions">' +
        btn("Start new search", "reset-confirm", "primary") +
        btn("Keep current search", "close-dialog", "text-button") +
        "</div>",
    );
  else go("entry");
}
async function download() {
  try {
    const data = await api(`/reports/${state.reportId}/source.json`);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `surrealestate-${state.reportId}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    closeDialog();
    announce("Source JSON downloaded.");
  } catch (e) {
    document
      .getElementById("dialog-body")
      .insertAdjacentHTML(
        "beforeend",
        `<p class="error" role="alert">${esc(e.message)}</p>`,
      );
  }
}
main.addEventListener("submit", (e) => {
  if (e.target.id === "address-form") {
    e.preventDefault();
    locate();
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "address") {
    state.address = e.target.value;
    state.confirmed = false;
    state.geocoded = false;
    state.candidates = [];
    state.chosen = null;
    state.requestId = null;
    save();
  }
  if (e.target.id === "saved-search") {
    state.query = e.target.value;
    document.getElementById("saved-results").innerHTML = savedResults();
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "status-filter") {
    state.statusFilter = e.target.value;
    render();
    document.getElementById("status-filter")?.focus({ preventScroll: true });
  }
  if (e.target.name === "candidate") {
    state.chosen = e.target.value;
    state.requestId = null;
    document.querySelector('[data-action="confirm"]').disabled = false;
  }
  if (["apis", "local", "dining"].includes(e.target.name)) {
    state.channels[e.target.name] = e.target.checked;
    state.requestId = null;
    save();
    document.querySelector('[data-action="generate"]').disabled =
      !hasChannels();
  }
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-action]");
  if (!b || b.disabled) return;
  const a = b.dataset.action;
  if (a === "home" || a === "saved") go(a);
  else if (a === "start") go(running() ? `progress/${running().id}` : "entry");
  else if (a === "new") newSearch();
  else if (a === "reset-confirm") {
    state.address = "";
    state.confirmed = false;
    state.chosen = null;
    state.candidates = [];
    state.geocoded = false;
    state.requestId = null;
    state.channels = { apis: true, local: false, dining: false };
    save();
    go("entry");
  } else if (a === "fill-example") {
    state.address = "414 Grant Street, Pittsburgh, PA 15219";
    state.confirmed = false;
    state.geocoded = false;
    state.candidates = [];
    state.chosen = null;
    state.requestId = null;
    save();
    render();
    document.getElementById("address").focus();
  } else if (a === "confirm") {
    state.confirmed = true;
    go("channels");
  } else if (a === "edit-address") go("entry");
  else if (a === "back-confirm") go("confirm");
  else if (a === "generate") generate();
  else if (a === "capabilities") checkCapabilities();
  else if (a === "resume-progress")
    go(`progress/${running()?.id || state.job?.id}`);
  else if (a === "preview") go(`report/${state.previewId}`);
  else if (a === "open") go(`report/${b.dataset.id}`);
  else if (a === "watch") go(`progress/${b.dataset.id}`);
  else if (a === "reconnect") {
    clearTimeout(timer);
    poll(state.job?.id || location.hash.split("/")[1], routeVersion);
  } else if (a === "retry" || a === "research-again") {
    const job = state.job;
    state.address = a === "retry" ? job.address : state.bench.case.address;
    if (a === "retry")
      state.channels = {
        apis: (job.channels || []).includes("apis"),
        local: (job.topics || []).includes("neighborhood_discussion"),
        dining: (job.topics || []).includes("restaurant_reviews"),
      };
    else
      state.channels = {
        apis: state.bench.coverage.some((item) => item.channel === "apis"),
        local: state.bench.case.priorities.includes("neighborhood_discussion"),
        dining: state.bench.case.priorities.includes("restaurant_reviews"),
      };
    state.requestId = null;
    state.confirmed = false;
    state.geocoded = false;
    state.candidates = [];
    state.chosen = null;
    save();
    go("entry");
  } else if (a === "report-nav") {
    state.nav = b.dataset.nav;
    state.selected = null;
    render();
    main
      .querySelector(`[data-nav="${state.nav}"]`)
      ?.focus({ preventScroll: true });
  } else if (a === "filter") {
    state.filter = b.dataset.filter;
    state.selected = null;
    render();
    main
      .querySelector(`[data-filter="${state.filter}"]`)
      ?.focus({ preventScroll: true });
  } else if (a === "map-category") {
    state.mapCategory = b.dataset.category;
    document.getElementById("spatial-overview").innerHTML = spatialOverview();
    (
      document.querySelector(`[data-category="${state.mapCategory}"]`) ||
      document.querySelector("[data-category]")
    )?.focus({ preventScroll: true });
  } else if (a === "evidence") openEvidence(b.dataset.id, b);
  else if (a === "review-gap") {
    state.nav = "Unresolved";
    render();
    main.querySelector(".panel-title")?.focus();
  } else if (a === "close-evidence") {
    if (dialog.open) {
      closeDialog();
      return;
    }
    state.selected = null;
    document.getElementById("inspector").innerHTML = evidence(null);
    document
      .querySelectorAll(".finding")
      .forEach((x) => x.classList.remove("selected"));
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
  } else if (a === "close-dialog") closeDialog();
  else if (a === "clear-search") {
    state.query = "";
    render();
    document.getElementById("saved-search").focus();
  } else if (a === "export")
    openDialog(
      "Export saved source JSON",
      '<p>The download contains the complete report, including all retained research channels and source details.</p><div class="actions">' +
        btn("Download JSON", "download", "primary") +
        btn("Cancel", "close-dialog", "text-button") +
        "</div>",
    );
  else if (a === "download") download();
});
dialog.addEventListener("cancel", (e) => {
  e.preventDefault();
  closeDialog();
});
dialog.addEventListener("click", (e) => {
  if (e.target === dialog) {
    const r = dialog.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      closeDialog();
  }
});
window.addEventListener("keydown", (e) => {
  if (
    e.key === "Escape" &&
    !dialog.open &&
    state.page === "report" &&
    state.selected
  )
    document.querySelector('[data-action="close-evidence"]')?.click();
});
window.addEventListener("hashchange", route);
(async () => {
  render();
  try {
    await refresh();
    const pending = state.runs.find(
      (run) => run.request_id === state.requestId && state.requestId,
    );
    if (pending && ["#channels", "#entry"].includes(location.hash)) {
      history.replaceState(null, "", `/#progress/${pending.id}`);
    }
  } catch (e) {
    state.error = e.message;
    render();
  }
  checkCapabilities();
  await route();
})();
