"use strict";
// The approved prototype supplies composition and tokens, never research data.
const showcase = window.SURREAL_SHOWCASE || (document.documentElement.dataset.showcase === "true" ? {contactEmail: ""} : null);
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
  sidebarCollapsed: false,
  mobileSidebarOpen: false,
  nav: "Findings",
  filter: "Location overview",
  mapCategory: "all",
  statusFilter: "All statuses",
  selected: null,
  researchTopic: null,
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
async function api(path, body, method = body ? "POST" : "GET") {
  if (showcase) {
    if (method !== "GET") throw new Error("This public showcase is read-only.");
    if (path === "/api/capabilities") return { web: { available: false } };
    if (path === "/api/runs") {
      const response = await fetch(new URL("data/manifest.json", document.baseURI));
      if (!response.ok) throw new Error("Sample reports are unavailable. Please reload.");
      const manifest = await response.json();
      return { runs: manifest.reports.map(r => ({...r, status: "complete", demo: false})), csrf: null };
    }
    const match = path.match(/^\/reports\/([a-z0-9-]+)\/bench\.json$/);
    if (!match || !state.runs.some(r => r.id === match[1])) throw new Error("Sample report not found.");
    path = new URL(`data/reports/${match[1]}.json`, document.baseURI);
  }
  let response;
  try {
    response = await fetch(path, {
      cache: "no-store",
      ...(method !== "GET"
        ? {
            method,
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": state.csrf,
            },
            ...(body ? { body: JSON.stringify(body) } : {}),
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
function contactSection() {
  return showcase ? `<section class="value-section showcase-contact" id="contact"><h2>Want to research an address?</h2><p>This public showcase contains real reports captured on their displayed dates. Live research runs privately; get in touch for a demonstration or to discuss the project.</p><a class="contact-link" href="mailto:${esc(showcase.contactEmail)}">${esc(showcase.contactEmail)}</a></section>` : "";
}
function home() {
  const p = state.preview;
  return `<section class="hero"><h1>Know the place<br>behind the address.</h1><p class="lede">Public records, nearby places and local intelligence. One report, with the evidence close at hand.</p><div class="hero-actions">${showcase ? btn('Explore sample reports <span aria-hidden="true">→</span>', "saved", "primary") : btn('Research an address <span aria-hidden="true">→</span>', "start", "primary")}${p ? btn(showcase ? "Open featured report" : "Explore saved report", "preview", "text-button") : ""}</div>${showcase ? '<p class="caption showcase-note">A public showcase of real Pittsburgh research. No live generation or sign-in required.</p>' : ""}</section><section class="preview-wrap" aria-label="Location overview preview"><div class="preview"><div class="preview-bar"><span>${p ? esc(p.case.address) : "Your research, in one place"}</span><span>${p ? date(p.case.as_of) : "Location overview"}</span></div><div class="location-preview"><h2>Location overview</h2>${p ? spatialOverview(p, false) : '<p class="preview-empty">Research an address to explore nearby places on a map, then follow each finding to its source.</p>'}${p ? btn("Explore this report", "preview", "text-button preview-open") : ""}</div></div></section><section class="value-section" aria-label="About SurrealEstate"><div class="value-line"><h2>Find what matters.</h2><p>Explore mapped surroundings, property and street records, and local intelligence drawn from discussions, reviews and other web sources.</p></div><div class="value-line"><h2>Follow the evidence.</h2><p>Read the brief, select a paragraph, and inspect the original source behind it. Coverage and missing information stay visible alongside the findings.</p></div><details class="coverage"><summary>Where does SurrealEstate have coverage?</summary><p>Property and permit coverage focuses on Pittsburgh. Mapped places and other sources vary by location. Unavailable research is identified in each report.</p></details></section>${contactSection()}`;
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
  return `<section class="setup">${step("Research")}<h1>What should we research?</h1><div class="address-context"><span>${esc(chosen()?.address || state.address)}</span>${btn("Edit", "edit-address", "text-button small-button", state.busy ? "disabled" : "")}</div><label class="channel"><input type="checkbox" name="apis" ${state.channels.apis ? "checked" : ""} ${state.busy ? "disabled" : ""}><span><strong>Public records & nearby places</strong><p>Property and permit records, mapped surroundings and street-closure permits.</p></span></label><p class="group-label">Local intelligence</p>${!state.capabilitiesLoaded ? '<p class="muted" role="status">Checking availability…</p>' : !state.webAvailable ? `<p class="error" role="status">Local intelligence is unavailable for this session.</p>${btn("Check again", "capabilities", "text-button small-button")}` : ""}${[
    [
      "local",
      "Local discussions",
      "Accounts and perspectives from local discussions.",
    ],
    [
      "dining",
      "Dining reviews",
      "Nearby restaurants and themes from reviews.",
    ],
  ]
    .map(
      ([k, t, d]) =>
        `<label class="channel"><input type="checkbox" name="${k}" ${state.channels[k] ? "checked" : ""} ${!state.webAvailable || state.busy ? "disabled" : ""}><span><strong>${t}</strong><p>${d}</p></span></label>`,
    )
    .join(
      "",
    )}<details class="location-detail"><summary>How web research works</summary><p>Tavily finds source material. A local AI plans research and checks factual uncertainties; Gemini writes a source-cited brief from the supplied material, without web search. Opinions and AI assessments remain distinct from public records.</p></details>${errorHTML()}<div class="actions">${btn(state.busy ? "Starting research…" : "Generate report", "generate", "primary", hasChannels() && !state.busy ? "" : "disabled")}${btn("Back", "back-confirm", "text-button", state.busy ? "disabled" : "")}</div></section>`;
}
function progress() {
  const j = state.job;
  return `<section class="setup" id="progress-screen"><div class="eyebrow" id="progress-state">${!j ? "Loading research" : j.status === "running" ? "Research in progress" : j.status === "failed" ? "Research interrupted" : "Report ready"}</div><h1>${esc(addressParts(j?.address || "Your research").street)}</h1><p class="lede">${esc(j?.geography || "")}</p><div class="status-list" aria-live="polite">${(j?.progress?.steps || []).map((s) => `<div class="status-row" data-step="${esc(s.id)}"><span class="status-mark ${s.state === "done" ? "done" : ""}" aria-hidden="true">${s.state === "done" ? "✓" : s.state === "active" ? '<span class="spinner"></span>' : s.state === "waiting" ? "○" : "—"}</span><span>${esc(s.label)}</span><small>${esc({ done: "Finished", active: "In progress", waiting: "Waiting", stopped: "Stopped", skipped: "Not run" }[s.state] || s.state)}</small></div>`).join("")}</div><p class="status-message">${esc(j?.status === "running" ? j.progress?.detail || j.message : j?.message || "Loading…")}</p><div id="progress-error">${errorHTML()}</div><div class="actions" id="progress-actions">${j?.status === "complete" ? btn("Explore report", "open", "primary", `data-id="${j.id}"`) : ""}${j?.status === "failed" ? btn("Try again", "retry", "primary") : ""}${state.error ? btn("Reconnect", "reconnect", "secondary") : ""}</div></section>`;
}
function updateProgress() {
  const current = document.getElementById("progress-screen");
  const template = document.createElement("template");
  template.innerHTML = progress();
  const next = template.content.firstElementChild;
  for (const selector of [
    "#progress-state",
    "h1",
    ".lede",
    ".status-message",
  ]) {
    const old = current.querySelector(selector),
      fresh = next.querySelector(selector);
    if (old.textContent !== fresh.textContent)
      old.textContent = fresh.textContent;
  }
  const oldRows = [...current.querySelectorAll(".status-row")];
  const newRows = [...next.querySelectorAll(".status-row")];
  if (
    oldRows.map((r) => r.dataset.step).join("|") !==
    newRows.map((r) => r.dataset.step).join("|")
  ) {
    current.querySelector(".status-list").replaceChildren(...newRows);
  } else
    oldRows.forEach((row, i) => {
      const replacements = [...newRows[i].children];
      for (let j = 0; j < row.children.length; j++) {
        const old = row.children[j],
          replacement = replacements[j];
        if (old.outerHTML !== replacement.outerHTML)
          old.replaceWith(replacement);
      }
    });
  for (const selector of ["#progress-error", "#progress-actions"]) {
    const old = current.querySelector(selector),
      fresh = next.querySelector(selector);
    if (old.innerHTML !== fresh.innerHTML)
      old.replaceChildren(...fresh.childNodes);
  }
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
  return `<div class="evidence-section"><h3>${w.label === "model_assessment" ? "AI review" : "Web summary"}</h3><p class="caption">Model-reported · not independently verified${r.truncated ? " · Response incomplete" : ""}</p><details><summary>Read ${w.label === "model_assessment" ? "the AI review" : "the summary"}</summary><div class="web-prose">${w.rendered_html}</div></details>${r.search_entry_point ? `<p class="caption">Google Search Suggestions</p><iframe class="suggestions" title="Google Search Suggestions" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" srcdoc="${esc(r.search_entry_point)}"></iframe>` : ""}<details><summary>Sources and cited answer passages</summary>${r.chunks.map((c, i) => `<div class="record"><strong>Source ${i + 1}</strong>${link(c.uri, c.title || "Open source") || "<p>Source URL not supplied</p>"}</div>`).join("")}${r.supports.map((s) => `<div class="record"><p>${esc(s.text)}</p><p class="caption">Sources: ${s.chunk_indices.map((i) => i + 1).join(", ") || "Not supplied"}</p></div>`).join("")}${raw(r, "Full saved response")}</details></div>`;
}
const researchTitles = { neighborhood_discussion: "Local discussions", restaurant_reviews: "Dining reviews" };
function selectedWebFinding(id) {
  for (const research of state.bench?.research || []) {
    const finding = research.findings.find((f) => f.ui_id === id);
    if (finding) return { research, finding };
    if (research.brief) {
      const paragraphs = [{ heading: "Brief overview", paragraph: research.brief.overview }, ...research.brief.sections.flatMap((section) => section.paragraphs.map((paragraph) => ({ heading: section.heading, paragraph })))];
      const entry = paragraphs.find((entry) => entry.paragraph.ui_id === id);
      if (entry) return { research, finding: { title: entry.heading, kind: "synthesized brief", assessment: "source linked", explanation: "", citations: entry.paragraph.citations } };
    }
  }
  return null;
}
function webFindingEvidence(research, finding) {
  const groups = [...new Set(finding.citations.map((c) => c.evidence_id))].map((id) => ({ evidence_id: id, excerpts: [...new Set(finding.citations.filter((c) => c.evidence_id === id).map((c) => c.excerpt))] }));
  return `<div class="evidence-head">${btn("Close", "close-evidence", "text-button small-button")}</div><h2 class="evidence-title" tabindex="-1">${esc(finding.title)}</h2><p class="caption">${esc(finding.kind.replaceAll("_", " "))} · ${esc(finding.assessment.replaceAll("_", " "))} · AI assessment</p>${finding.explanation ? `<p class="evidence-summary">${esc(finding.explanation)}</p>` : ""}${groups.map((c) => {
    const source = state.bench.evidence.find((e) => e.id === c.evidence_id);
    if (!source) return "";
    return `<section class="evidence-section"><h3>${esc(source.title)}</h3>${c.excerpts.map((excerpt) => `<blockquote>${esc(excerpt)}</blockquote>`).join("")}<p class="caption">${esc(source.attribution || "Web source")} · ${source.source_updated_at ? date(source.source_updated_at) : "Publication date not supplied"}</p><p class="caption">${source.details.content_kind === "mixed" ? "Returned page content and search passages" : source.details.content_kind === "page_content" ? "Returned page content" : "Search passage; complete page unavailable"}</p>${link(source.uri, "Read original source")}<details><summary>Retrieval details</summary>${metadata(source)}</details></section>`;
  }).join("")}${btn("Read full research", "read-research", "secondary", `data-topic="${esc(research.topic)}"`)}`;
}
function synthesizedBrief(r) {
  const brief = r.brief;
  const paragraph = (p) => {
    const ids = [...new Set(p.citations.map((c) => c.evidence_id))];
    return `<div class="brief-paragraph ${state.selected === p.ui_id ? "selected" : ""}" id="${esc(p.ui_id)}"><p>${esc(p.text)} <span class="brief-inline-sources" aria-label="Paragraph sources">${ids.map((id) => { const source = state.bench.evidence.find((e) => e.id === id); const number = r.evidence_ids.indexOf(id) + 1; return source ? link(source.uri, `[${number}]`) : ""; }).join(" ")}</span></p>${btn('<span class="sr-only">View paragraph sources</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg>', "evidence", "brief-evidence-trigger", `data-id="${esc(p.ui_id)}" aria-pressed="${state.selected === p.ui_id}"`)}</div>`;
  };
  const used = new Set([brief.overview, ...brief.sections.flatMap((s) => s.paragraphs)].flatMap((p) => p.citations.map((c) => c.evidence_id)));
  return `<article class="synthesized-brief" aria-label="Synthesized research brief"><p class="caption brief-byline">Written with ${esc(brief.model)} · Sources retrieved by Tavily · ${date(brief.generated_at)}</p><p class="caption brief-hint">Select a paragraph to view its sources.</p>${paragraph(brief.overview)}${brief.sections.map((section) => `<section class="brief-section"><h3>${esc(section.heading)}</h3>${section.paragraphs.map(paragraph).join("")}</section>`).join("")}<details class="brief-source-list"><summary>Sources cited in this brief</summary>${r.evidence_ids.filter((id) => used.has(id)).map((id) => { const source = state.bench.evidence.find((e) => e.id === id); return source ? `<div class="record">${link(source.uri, `[${r.evidence_ids.indexOf(id) + 1}] ${source.title}`)}<p class="caption">${source.source_updated_at ? date(source.source_updated_at) : "Publication date not supplied"}</p></div>` : ""; }).join("")}</details></article>`;
}
function researchReader() {
  const b = state.bench;
  const topics = [...new Set([...(b.research || []).map((r) => r.topic), ...b.web.map((w) => w.topic), ...b.findings.filter((f) => f.research_topic).map((f) => f.topic)])];
  if (!topics.length) return '<p class="empty-state">Local intelligence was not selected for this report.</p>';
  if (!topics.includes(state.researchTopic)) state.researchTopic = topics[0];
  const topic = state.researchTopic;
  const r = (b.research || []).find((r) => r.topic === topic);
  const legacy = b.web.filter((w) => w.topic === topic);
  const tabs = `<nav class="research-tabs" aria-label="Local intelligence topics">${topics.map((t) => btn(researchTitles[t] || t, "research-topic", "", `data-topic="${esc(t)}" aria-pressed="${t === topic}"`)).join("")}</nav>`;
  let content;
  if (r) {
    content = `<p class="research-intro">${r.brief ? `Research brief · ${r.evidence_ids.length} sources` : `${r.findings.length} extraction notes · ${r.evidence_ids.length} sources`}</p>${!r.brief ? `<p class="caption">${r.synthesis_status === "error" ? "Final writing was unavailable. Source-linked research notes are shown below." : "This saved report contains extraction notes. New runs include a synthesized brief."}</p>` : ""}${r.brief ? synthesizedBrief(r) : r.findings.map((f) => `<article class="research-finding ${state.selected === f.ui_id ? "selected" : ""}" id="${f.ui_id}"><div class="research-finding-head"><h3>${esc(f.title)}</h3><span class="research-kind">${esc(f.kind.replaceAll("_", " "))}</span></div><p>${esc(f.statement)}</p>${f.location_relevance ? `<p class="caption">${esc(f.location_relevance)}</p>` : ""}${f.assessment !== "reported" || f.explanation ? `<p class="research-assessment ${f.assessment === "conflicting" ? "has-conflict" : ""}"><strong>${esc(f.assessment.replaceAll("_", " "))} · AI assessment</strong>${f.explanation ? ` — ${esc(f.explanation)}` : ""}</p>` : ""}<div class="research-citations">${btn(`Inspect ${f.citations.length === 1 ? "source" : "sources"}`, "evidence", "secondary small-button", `data-id="${f.ui_id}" aria-pressed="${state.selected === f.ui_id}"`)}${f.citations.map((c, i) => {const source = b.evidence.find((e) => e.id === c.evidence_id); return source ? link(source.uri, `[${i + 1}] ${source.attribution || source.title}`) : "";}).join("")}</div></article>`).join("")}${!r.brief && !r.findings.length ? '<p class="empty-state">No supported findings were produced. Returned sources remain available below.</p>' : ""}${[...new Set([...r.limitations, ...(r.brief?.limitations || [])])].length ? `<section class="research-notes"><h3>Limits of this research</h3><ul>${[...new Set([...r.limitations, ...(r.brief?.limitations || [])])].map((x) => `<li>${esc(x)}</li>`).join("")}</ul></section>` : ""}${[...new Set([...r.follow_up_questions, ...(r.brief?.follow_up_questions || [])])].length ? `<section class="research-notes"><h3>Questions to explore next</h3><ul>${[...new Set([...r.follow_up_questions, ...(r.brief?.follow_up_questions || [])])].map((x) => `<li>${esc(x)}</li>`).join("")}</ul></section>` : ""}<details class="research-scope"><summary>Sources & search scope</summary><p>${r.search_calls} search requests · ${r.usage_credits} Tavily credits reported.</p>${r.evidence_ids.map((id) => {const e = b.evidence.find((e) => e.id === id); return e ? `<div class="record">${link(e.uri, e.title)}<p class="caption">${e.source_updated_at ? date(e.source_updated_at) : "Publication date not supplied"}</p>${btn("Inspect source", "evidence", "text-button small-button", `data-id="${esc(id)}"`)}</div>` : "";}).join("")}<details><summary>Search queries</summary><ul>${r.queries.map((q) => `<li>${esc(q)}</li>`).join("")}</ul></details></details>`;
  } else if (legacy.length) {
    content = `<p class="caption">Saved Gemini research · model-reported, not independently verified. Cited answer passages are not original source excerpts.</p>${legacy.map((w) => `<section class="legacy-research"><h3>${w.label === "model_assessment" ? "AI re-check" : "Original research"}</h3>${w.response.truncated ? '<p class="error">This saved response is incomplete.</p>' : ""}<div class="web-prose">${w.rendered_html}</div>${w.response.search_entry_point ? `<p class="caption">Associated Google Search Suggestions</p><iframe class="suggestions" title="Google Search Suggestions" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" srcdoc="${esc(w.response.search_entry_point)}"></iframe>` : ""}<details><summary>Sources for this response</summary>${w.response.chunks.map((c, i) => `<div class="record">${link(c.uri, `[${i + 1}] ${c.title || "Source"}`)}</div>`).join("")}</details></section>`).join("")}`;
  } else {
    content = `<p class="empty-state">No research brief was returned.</p>${b.coverage.filter((c) => c.topic === topic).map((c) => `<p>${esc(c.reason)}</p>`).join("")}`;
  }
  return `<section class="research-reader">${tabs}<h2 class="research-title" tabindex="-1">${esc(researchTitles[topic] || topic)}</h2>${content}</section>`;
}
function openResearch(topic) {
  closeDialog(false);
  state.nav = "Local intelligence";
  state.researchTopic = topic;
  state.selected = null;
  state.mobileSidebarOpen = false;
  render();
  main.querySelector(".research-title")?.focus({ preventScroll: true });
}
function evidence(id) {
  const b = state.bench;
  const webFinding = selectedWebFinding(id);
  if (webFinding) return webFindingEvidence(webFinding.research, webFinding.finding);
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
  return `<dl class="scope-list"><div><dt>Address</dt><dd>${esc(b.case.address)}</dd></div><div><dt>Report date</dt><dd>${date(b.case.as_of)}</dd></div><div><dt>Research</dt><dd>${[...new Set(b.findings.map((f) => f.section === "Web research" ? "Local intelligence" : f.section))].map(esc).join("<br>")}</dd></div></dl><div class="actions">${showcase ? btn("Get in touch", "contact", "secondary") : btn("Export source JSON", "export", "secondary") + btn("Research again", "research-again", "text-button")}</div>`;
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
function mappedCategories(bench = state.bench) {
  return mapCategoryStyles.flatMap((c) => {
    const source = bench.evidence.find(
      (e) =>
        e.provider === "openstreetmap" &&
        e.details?.category === c.id &&
        Array.isArray(e.details.members),
    );
    return source
      ? [{ ...c, evidenceId: source.id, details: source.details }]
      : [];
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
    mapped_amenities: "Mapped surroundings",
    street_closures: "Street-closure permits",
    neighborhood_discussion: "Local discussions",
    restaurant_reviews: "Dining reviews",
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
      topic,
      title: esc(titles[topic] || finding?.title || topic.replaceAll("_", " ")),
      outcome: esc(outcome),
      id: finding ? `overview-${topic}` : null,
      status,
    };
  });
}
function mapCategorySummary(categories, selected) {
  const category = categories.find((c) => c.id === selected);
  if (!category)
    return `<div class="map-summary"><p>Select a category to explore its locations and source.</p><p class="caption">Community-mapped features · straight-line distances, not travel distances.</p></div>`;
  const d = category.details;
  return `<div class="map-summary"><p>${d.count_is_lower_bound ? "At least " : ""}${esc(d.mapped_feature_count ?? d.members.length)} mapped features${Number.isFinite(d.query_radius_m) ? ` within ${esc(distanceLabel(d.query_radius_m))}` : " retained"}.${d.count_is_lower_bound ? " Results capped." : ""}</p><p class="caption">Straight-line distances to mapped points or centres.</p>${btn("View locations & source", "evidence", "link-button map-evidence", `data-id="${esc(category.evidenceId)}"`)}</div>`;
}
function spatialOverview(bench = state.bench, interactive = true) {
  const mapCategories = mappedCategories(bench);
  const origin = bench.evidence
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
  const selected = interactive ? state.mapCategory || "all" : "all";
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
  const mapCache = groups.find((c) => c.details.cached_response_retrieved_at)?.details;
  const cacheNotice = mapCache ? `<p class="map-caption${mapCache.cache_stale ? ' error' : ''}">${mapCache.cache_stale ? 'Live map refresh unavailable. Showing saved map data' : 'Using cached map data'} from ${date(mapCache.cached_response_retrieved_at)}.</p>` : "";
  return `<div class="spatial-card"><div class="spatial-plot"><svg viewBox="0 0 520 520" role="img" aria-labelledby="map-title map-description"><title id="map-title">Mapped places around ${esc(bench.case.address)}</title><desc id="map-description">North-up coordinate plot of saved OpenStreetMap feature centres, with a distance reference circle around the estimated address point. Category totals and an accessible location list follow.</desc><defs><clipPath id="mapclip"><rect x="12" y="12" width="496" height="496" rx="4"/></clipPath></defs><g class="map-grid" fill="none" stroke="#DADAE0" stroke-width="0.6">${[60, 160, 260, 360, 460].map((v) => `<path d="M${v} 0V520M0 ${v}H520"/>`).join("")}</g><circle cx="260" cy="260" r="218" fill="none" stroke="#858591" stroke-width="1.3" stroke-dasharray="5 6" class="search-radius"/><g clip-path="url(#mapclip)">${markers}</g><circle cx="260" cy="260" r="12" fill="#FFFFFF" stroke="#303038" stroke-width="2" class="address-ring"/><circle cx="260" cy="260" r="4" fill="#303038" class="address-dot"/><text x="390" y="76" fill="#60606B" font-size="12" class="map-label">${esc(distanceLabel(radius))}</text><path d="M487 47V23m-4 6 4-6 4 6" fill="none" stroke="#858591" class="north-arrow"/><text x="482" y="64" fill="#60606B" font-size="12" class="map-label">N</text><path d="M26 489h109m-109-4v8m109-8v8" fill="none" stroke="#858591" class="scale-line"/><text x="27" y="476" fill="#60606B" font-size="12" class="map-label">${esc(distanceLabel(radius / 2))}</text></svg></div><div class="map-context"><div class="map-legend" aria-label="Mapped place categories">${mapCategories
    .map((c) => {
      const d = c.details;
      return btn(
        `<span class="legend-inner"><span class="legend-symbol ${c.shape}" style="--marker:${c.color}" aria-hidden="true"></span><strong>${d.count_is_lower_bound ? "≥" : ""}${esc(d.mapped_feature_count ?? d.members.length)}</strong><span>${c.label}</span></span>`,
        interactive ? "map-category" : "preview",
        "legend-row",
        `data-category="${c.id}" aria-pressed="${selected === c.id}" aria-label="${interactive ? `Show ${c.label.toLowerCase()} on map` : `Explore ${c.label.toLowerCase()} in this report`}"`,
      );
    })
    .join(
      "",
    )}${selected !== "all" ? btn("Show all places", "map-category", "text-button map-reset", 'data-category="all"') : ""}</div>${interactive ? mapCategorySummary(mapCategories, selected) : '<div class="map-summary"><p>Nearby places, in context.</p><p class="caption">Open the report to explore each category and its evidence.</p></div>'}<p class="map-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a></p></div></div>${mapCache?.cache_stale ? cacheNotice : ""}<details class="location-detail place-list"><summary>View mapped locations</summary>${mapCache?.cache_stale ? "" : cacheNotice}<div class="table-scroll"><table class="overview-table"><thead><tr><th>Place</th><th>Category</th><th>Distance</th></tr></thead><tbody>${groups.flatMap((c) => c.details.members.map((m) => `<tr><td>${link(m.uri, m.name || "Unnamed mapped feature") || esc(m.name || "Unnamed mapped feature")}</td><td>${c.label}</td><td>${Number.isFinite(m.approximate_center_distance_m) ? "~" + Math.round(m.approximate_center_distance_m) + " m" : "Distance unavailable"}</td></tr>`)).join("")}</tbody></table></div><p>Distances are straight-line measurements to mapped points or centres, not travel distances. Counts describe retained mapped features, not necessarily distinct facilities. Capped categories are lower bounds. Features without saved coordinates appear only in the list. The dashed circle is a distance reference, not a property boundary.</p></details>`;
}
function researchPreviews(rows) {
  const b = state.bench;
  const topics = [...new Set([...(b.research || []).map((r) => r.topic), ...b.web.map((w) => w.topic), ...b.findings.filter((f) => f.section === "Web research").map((f) => f.topic), ...b.coverage.filter((c) => c.channel === "web").map((c) => c.topic)])];
  if (!topics.length) return '<section class="overview-section"><h2>Local intelligence</h2><p class="empty-state">Local intelligence was not selected for this report.</p></section>';
  return `<section class="overview-section research-previews" aria-label="Local intelligence previews"><h2>Local intelligence</h2>${topics.map((topic) => {
    const research = (b.research || []).find((r) => r.topic === topic);
    const row = rows.find((r) => r.topic === topic);
    const text = research?.brief?.overview.text || research?.findings[0]?.statement;
    const sentence = text?.split(/(?<=[.!?])\s+(?=[A-Z])/)[0];
    const excerpt = sentence && sentence.length > 360 ? sentence.slice(0, 360).replace(/\s+\S*$/, "") + "…" : sentence;
    const status = row?.status || "Unknown";
    const label = research?.brief ? "Read brief" : "View research";
    return `<article class="research-preview"><div class="research-preview-heading"><h3>${esc(researchTitles[topic] || topic.replaceAll("_", " "))}</h3><span class="status-label status-${status.toLowerCase()}">${status}</span></div><p>${excerpt ? esc(excerpt) : row?.outcome || "No research summary was retained."}</p>${research?.synthesis_status === "error" ? '<p class="caption">Final brief unavailable; research notes and sources are available.</p>' : ""}${btn(`${label}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h16m-6-6 6 6-6 6"/></svg>`, "read-research", "text-button research-preview-link", `data-topic="${esc(topic)}" aria-label="${label}: ${esc(researchTitles[topic] || topic)}"`)}</article>`;
  }).join("")}</section>`;
}
function locationOverview() {
  return `<section class="overview-section" aria-label="Location overview"><h2>Location overview</h2><div id="spatial-overview">${spatialOverview()}</div></section>`;
}
function reportCoverage() {
  const rows = overviewRows();
  const shown = rows.filter(
    (r) =>
      !state.statusFilter ||
      state.statusFilter === "All statuses" ||
      r.status === state.statusFilter,
  );
  return `<section class="overview-section" aria-label="Report coverage"><div class="overview-heading"><h2>Report coverage</h2><label><span class="sr-only">Filter research status</span><select id="status-filter">${["All statuses", "Complete", "Blocked", "Limited", "Failed", "Unavailable", "Unknown"].map((v) => `<option ${v === (state.statusFilter || "All statuses") ? "selected" : ""}>${v}</option>`).join("")}</select></label></div><div class="table-scroll research-table" tabindex="0" role="region" aria-label="Research status table"><table class="overview-table"><thead><tr><th>Research</th><th>Outcome</th><th>Status</th></tr></thead><tbody>${shown.length ? shown.map((r) => `<tr><th scope="row">${!r.id ? r.title : btn(r.title, "evidence", "table-topic", `data-id="${r.id}"`)}</th><td>${r.outcome}</td><td><span class="status-label status-${r.status.toLowerCase().replace(" ", "-")}">${r.status}</span></td></tr>`).join("") : `<tr><td colspan="3" class="empty-status">No ${esc((state.statusFilter || "").toLowerCase())} research recorded in this report.</td></tr>`}</tbody></table></div><ul class="mobile-status-list" aria-label="Research status">${shown.length ? shown.map((r) => `<li><div class="mobile-status-heading">${!r.id ? `<strong>${r.title}</strong>` : btn(r.title, "evidence", "mobile-topic", `data-id="${r.id}"`)}<span class="status-label status-${r.status.toLowerCase().replace(" ", "-")}">${r.status}</span></div><p>${r.outcome}</p></li>`).join("") : `<li>No ${esc((state.statusFilter || "").toLowerCase())} research recorded in this report.</li>`}</ul><details class="location-detail"><summary>What these statuses mean</summary><p>Complete means the research finished, not that its claims are independently verified. Limited indicates capped results; blocked research needs missing information. Failed is a research error, while unavailable means a source could not be used. Unknown means no completion status was retained. A successful search with no matches is shown as complete with “No records found” in its outcome.</p></details></section>`;
}
const railIcons = {
  brand: "M3 19V8l9-5 9 5v11H3Zm9-16v16M3 8l9 5 9-5",
  collapse: "M4 4h16v16H4zM9 4v16m7-12-3 4 3 4",
  expand: "M4 4h16v16H4zM9 4v16m4-12 3 4-3 4",
  menu: "M4 6h16M4 12h16M4 18h16",
  Findings: "M5 3h14v18H5zM8 8h8M8 12h8M8 16h5",
  Unresolved: "M12 8v5m0 3v.1M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18",
  Sources: "M8 3h12v14H8zM4 7v14h12M11 7h6m-6 4h6",
  "Local intelligence": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm4 5-2.5 5.5L8 16l2.5-5.5L16 8Z",
  "Research scope": "M4 7h16M4 17h16M8 4v6m8 4v6",
  new: "M12 4v16M4 12h16",
  saved: "M4 4h16v16H4zM8 4v7l4-2 4 2V4",
  contact: "M3 5h18v14H3zM3 5l9 8 9-8",
  export: "M12 3v12m-4-4 4 4 4-4M4 15v6h16v-6",
};
const railIcon = (name) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${railIcons[name]}"/></svg>`;
function reportSidebar() {
  const mobile = matchMedia("(max-width:720px)").matches;
  const expanded = mobile ? state.mobileSidebarOpen : !state.sidebarCollapsed;
  const item = (label, action, icon, attrs = "") =>
    btn(
      `${railIcon(icon)}<span class="rail-label">${label}</span>${!expanded ? `<span class="rail-tooltip" role="tooltip" id="rail-tip-${label.toLowerCase().replaceAll(" ", "-")}">${label}</span>` : ""}`,
      action,
      "rail-item",
      `aria-label="${label}" ${!expanded ? `aria-describedby="rail-tip-${label.toLowerCase().replaceAll(" ", "-")}"` : ""} ${attrs}`,
    );
  const top = expanded
    ? `${btn(`${railIcon("brand")}<span class="rail-label">SurrealEstate</span>`, "home", "brand rail-brand", 'aria-label="SurrealEstate home" title="SurrealEstate home"')}${btn(railIcon("collapse"), "toggle-sidebar", "rail-toggle", 'aria-label="Collapse sidebar" aria-expanded="true" aria-controls="report-sidebar"')}`
    : btn(
        `<span class="rail-logo-default">${railIcon("brand")}</span><span class="rail-logo-expand">${railIcon("expand")}</span><span class="rail-tooltip" id="expand-sidebar-tip" role="tooltip">Expand sidebar</span>`,
        "toggle-sidebar",
        "rail-brand rail-logo-toggle",
        'aria-label="Expand sidebar" aria-describedby="expand-sidebar-tip" aria-expanded="false" aria-controls="report-sidebar"',
      );
  return `<aside class="report-rail" id="report-sidebar" ${mobile && expanded ? 'role="dialog" aria-modal="true" aria-label="Report navigation"' : ""}><div class="rail-top">${top}</div><nav class="rail-navigation" aria-label="Report">${["Findings", "Local intelligence", "Unresolved", "Sources", "Research scope"].map((n) => item(n, "report-nav", n, `data-nav="${n}" ${state.nav === n ? 'aria-current="page"' : ""}`)).join("")}${showcase ? "" : `<div class="rail-export">${item("Export JSON", "export", "export")}</div>`}</nav><nav class="rail-global" aria-label="Reports">${showcase ? item("Get in touch", "contact", "contact") : item(running() ? "View progress" : "New report", running() ? "resume-progress" : "new", "new")}${item(showcase ? "Sample reports" : "Saved reports", "saved", "saved")}</nav></aside>`;
}
function sidebarControls() {
  return `${btn(railIcon("menu"), "toggle-sidebar", "mobile-rail-toggle", `aria-label="Open sidebar" aria-expanded="${state.mobileSidebarOpen}" aria-controls="report-sidebar"`)}${btn("", "toggle-sidebar", "rail-scrim", 'aria-label="Close sidebar" tabindex="-1"')}`;
}
function sidebarShellClass() {
  return `report-shell${state.sidebarCollapsed ? " rail-collapsed" : ""}${state.mobileSidebarOpen ? " mobile-rail-open" : ""}`;
}
function syncSidebar() {
  const mobile = matchMedia("(max-width:720px)").matches;
  const open = state.page === "report" && mobile && state.mobileSidebarOpen;
  document.body.classList.toggle("sidebar-open", open);
  document.querySelector(".report-work")?.toggleAttribute("inert", open);
  document
    .querySelector(".report-shell > .report-inspector")
    ?.toggleAttribute("inert", open);
  const toolbar = document.querySelector(".mobile-rail-toggle");
  if (toolbar) toolbar.setAttribute("aria-expanded", String(open));
}
function toggleSidebar() {
  const mobile = matchMedia("(max-width:720px)").matches;
  if (mobile) state.mobileSidebarOpen = !state.mobileSidebarOpen;
  else state.sidebarCollapsed = !state.sidebarCollapsed;
  const shell = document.querySelector(".report-shell");
  shell.className = sidebarShellClass();
  document.getElementById("report-sidebar").outerHTML = reportSidebar();
  syncSidebar();
  const target =
    mobile && !state.mobileSidebarOpen
      ? ".mobile-rail-toggle"
      : "#report-sidebar [data-action=toggle-sidebar]";
  document.querySelector(target)?.focus({ preventScroll: true });
}
function report() {
  const b = state.bench;
  if (!b)
    return `<div class="${sidebarShellClass()}">${sidebarControls()}${reportSidebar()}<section class="report-work setup"><h1>Opening report…</h1>${errorHTML()}</section></div>`;
  const fs = findings(),
    gaps = fs.filter((f) => f.unresolved),
    onlyLimited = gaps.length && gaps.every((f) => f.coverage.length && f.coverage.every((c) => ["complete", "empty", "truncated"].includes(c.status)) && !f.research_topic),
    topics = ["Location overview", "Local intelligence", "Property & street records", "Report coverage"];
  if (!topics.includes(state.filter)) state.filter = "Location overview";
  const rows = fs.filter(
    (f) =>
      (state.nav !== "Unresolved" || f.unresolved) &&
      (state.nav !== "Findings" ||
        (state.filter === "Property & street records" &&
          ["Records", "Street permits"].includes(f.section))),
  );
  return `<div class="${sidebarShellClass()}">${sidebarControls()}${reportSidebar()}<section class="report-work"><header class="report-heading"><h1>${esc(addressParts(b.case.address).street)}</h1><p>${esc(addressParts(b.case.address).locality || b.case.geography)} · Report dated ${date(b.case.as_of)}${b.demo ? " · Synthetic demo" : ""}</p></header>${errorHTML()}${state.nav === "Findings" ? `${gaps.length ? `<div class="notice"><span>${onlyLimited ? `Limited coverage: ${gaps.map((f) => esc(f.title)).join(", ")}.` : gaps.length === 1 ? `${esc(gaps[0].title)} needs attention.` : `${gaps.length} research topics are unresolved.`}</span>${btn("Review", "review-gap")}</div>` : ""}<div class="filters" aria-label="Filter findings">${topics.map((t) => btn(t, "filter", "", `data-filter="${t}" aria-pressed="${state.filter === t}"`)).join("")}</div>${state.filter === "Property & street records" ? '<h2 class="records-title">Property &amp; street records</h2>' : ""}` : `<h2 class="panel-title" tabindex="-1">${state.nav}</h2>`}${
    state.nav === "Local intelligence"
      ? researchReader()
      : state.nav === "Sources"
      ? sources()
      : state.nav === "Research scope"
        ? scope()
        : state.nav === "Findings" && state.filter === "Location overview"
          ? locationOverview()
          : state.nav === "Findings" && state.filter === "Local intelligence"
            ? researchPreviews(overviewRows())
          : state.nav === "Findings" && state.filter === "Report coverage"
            ? reportCoverage()
          : rows.length
            ? rows
                .map(
                  (f) =>
                    `<article class="finding ${state.selected === f.id ? "selected" : ""}" id="${f.id}"><div><h2>${btn(esc(f.title), "evidence", "finding-select", `data-id="${f.id}" aria-label="Inspect evidence for ${esc(f.title)}" aria-pressed="${state.selected === f.id}"`)}</h2><p>${esc(f.statements[0] || "No finding returned.")}</p>${
                      f.statements.length > 1
                        ? `<details><summary>${f.statements.length - 1} more ${f.topic === "street_closures" ? "records" : "findings"}</summary>${f.statements
                            .slice(1)
                            .map((t) => `<p>${esc(t)}</p>`)
                            .join("")}</details>`
                        : ""
                    }<p class="qualifier">${esc(f.qualifier)}</p></div><svg class="finding-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg></article>`,
                )
                .join("")
            : `<p class="empty-state">${state.nav === "Unresolved" ? "No unresolved topics were recorded." : "No property or street records were returned for this report."}</p>`
  }</section><aside class="report-inspector" id="inspector" aria-label="Evidence inspector">${evidence(state.selected)}</aside></div>`;
}
function savedResults() {
  if (showcase) return state.runs.filter(r => `${r.address} ${r.label}`.toLowerCase().includes(state.query.trim().toLowerCase())).map(r => `<article class="saved-row"><div><h2>${esc(r.label)}</h2><p>${esc(addressParts(r.address).street)}</p><p>${esc(r.description)}</p>${r.review_note ? `<p class="caption">${esc(r.review_note)}</p>` : ""}<p class="caption">Report captured ${date(r.created_at)}</p></div><div class="saved-actions">${btn('Explore report <span aria-hidden="true">→</span>', "open", "secondary", `data-id="${esc(r.id)}"`)}</div></article>`).join("") || '<p class="empty-state">No sample reports match your search.</p>';
  const runs = state.runs.filter((r) =>
    r.address.toLowerCase().includes(state.query.trim().toLowerCase()),
  );
  return runs.length
    ? runs
        .map(
          (r) =>
            `<article class="saved-row"><div><h2>${esc(r.address)}</h2><p>${esc(r.geography || "")} · ${date(r.created_at)}</p><p>${r.demo ? "Synthetic demo · " : ""}${r.status === "complete" ? (r.partial ? "Some topics unresolved" : "Report ready") : r.status === "failed" ? "Research interrupted" : "Research in progress"}</p></div><div class="saved-actions">${btn(r.status === "complete" ? 'Open report <span aria-hidden="true">→</span>' : "View progress", r.status === "complete" ? "open" : "watch", "secondary", `data-id="${r.id}"`)}${r.status !== "running" ? btn("Delete", "delete-report", "text-button delete-report", `data-id="${r.id}" aria-label="Delete report for ${esc(r.address)}"`) : ""}</div></article>`,
        )
        .join("")
    : `<p class="empty-state">${state.query ? `No saved reports match “${esc(state.query)}”.` : "Your saved reports will appear here."}</p>${state.query ? btn("Clear search", "clear-search", "text-button") : ""}`;
}
async function deleteReport(identifier, button) {
  button.disabled = true;
  button.textContent = "Deleting…";
  try {
    await api(
      `/api/runs/${encodeURIComponent(identifier)}`,
      undefined,
      "DELETE",
    );
    state.runs = state.runs.filter((r) => r.id !== identifier);
    if (state.previewId === identifier) {
      state.preview = null;
      state.previewId = null;
    }
    if (state.reportId === identifier) {
      state.bench = null;
      state.reportId = null;
    }
    state.error = "";
    closeDialog(false);
    render();
    document.getElementById("saved-search")?.focus({ preventScroll: true });
    announce("Report deleted.");
  } catch (error) {
    button.disabled = false;
    button.textContent = "Delete report";
    document.getElementById("delete-error").textContent = error.message;
  }
}
function saved() {
  return `<section class="saved-page"><div class="saved-heading"><h1>${showcase ? "Sample reports" : "Saved reports"}</h1>${showcase ? btn("Get in touch", "contact", "text-button") : btn('New research <span aria-hidden="true">↗</span>', "new", "primary")}</div>${errorHTML()}<label for="saved-search" class="sr-only">${showcase ? "Search sample reports" : "Search saved reports"}</label><div class="saved-search"><input type="search" id="saved-search" value="${esc(state.query)}" placeholder="Search by address"></div><div id="saved-results">${savedResults()}</div>${showcase ? '<p class="caption">These are dated research examples, not live listings. Source limitations remain visible in each report.</p>' : ""}</section>`;
}
function render(focus = false) {
  document.body.classList.toggle("bench-page", state.page === "report");
  document.querySelector(".app-header").hidden = state.page === "report";
  document.body.classList.toggle(
    "research-flow",
    ["entry", "confirm", "channels", "progress"].includes(state.page),
  );
  document.querySelector('.app-header [data-action="saved"]').hidden =
    Boolean(showcase) || document.body.classList.contains("research-flow");
  if (state.page === "progress" && document.getElementById("progress-screen"))
    updateProgress();
  else
    main.innerHTML = `<div class="${state.page === "report" ? "report-view" : state.page === "progress" ? "progress-view" : "fade-in"}">${({ home, entry, confirm, channels, progress, report, saved }[state.page] || home)()}</div>`;
  syncSidebar();
  if (showcase && !document.querySelector(".header-github")) {
    document.querySelector(".app-header nav").insertAdjacentHTML("beforeend", '<a class="header-github" href="https://github.com/Lucas-Granucci/surreal-estate" target="_blank" rel="noopener noreferrer" aria-label="View SurrealEstate on GitHub" title="View on GitHub"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .8a11.2 11.2 0 0 0-3.54 21.83c.56.1.77-.24.77-.54v-2.1c-3.14.68-3.8-1.33-3.8-1.33-.51-1.3-1.25-1.65-1.25-1.65-1.02-.7.08-.68.08-.68 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.63 1.22 3.27.93.1-.73.39-1.22.71-1.5-2.5-.28-5.13-1.25-5.13-5.57 0-1.23.44-2.23 1.16-3.02-.12-.28-.5-1.43.11-2.98 0 0 .95-.3 3.08 1.15A10.7 10.7 0 0 1 12 6.12c.95 0 1.9.13 2.8.38 2.13-1.45 3.07-1.15 3.07-1.15.62 1.55.23 2.7.12 2.98.72.79 1.15 1.79 1.15 3.02 0 4.33-2.63 5.29-5.14 5.57.4.35.76 1.04.76 2.1v3.07c0 .3.2.65.78.54A11.2 11.2 0 0 0 12 .8Z"/></svg></a>');
  }
  const top = document.querySelector(".app-header nav .secondary");
  top.dataset.action = showcase ? "contact" : running() ? "resume-progress" : "new";
  top.innerHTML = showcase ? "Get in touch" : running()
    ? "View progress"
    : 'New research <span aria-hidden="true">↗</span>';
  document.title =
    (state.page === "report" && state.bench
      ? state.bench.case.address
      : state.page === "saved"
        ? (showcase ? "Sample reports" : "Saved reports")
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
  state.mobileSidebarOpen = false;
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
  if (showcase && !["home", "saved", "report"].includes(state.page)) state.page = "home";
  if (["confirm", "channels"].includes(state.page) && !state.geocoded)
    state.page = "entry";
  if (state.page === "channels" && !state.confirmed) state.page = "confirm";
  if (state.page === "report") {
    state.bench = null;
    state.mapCategory = "all";
    state.statusFilter = "All statuses";
    state.selected = null;
    state.nav = "Findings";
    state.filter = "Location overview";
  }
  if (page === "progress" && state.job?.id !== id) state.job = null;
  render(true);
  try {
    if (state.page === "report" && id) {
      const b = await api(`/reports/${encodeURIComponent(id)}/bench.json`);
      if (version !== routeVersion) return;
      state.bench = b;
      state.reportId = id;
      state.selected = null;
      state.researchTopic = null;
      render(true);
    } else if (!showcase && page === "progress" && id) {
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
  const topicFinding = id?.startsWith("overview-") ? overviewFinding(id.slice(9)) : state.bench.findings.find((f) => f.id === id);
  if (topicFinding?.research_topic || topicFinding?.web_indices?.length) {
    openResearch(topicFinding.research_topic || topicFinding.topic);
    return;
  }
  state.selected = id;
  if (document.getElementById("spatial-overview")) {
    const category = mappedCategories().find((c) => c.evidenceId === id);
    state.mapCategory = category?.id || "all";
    // Avoid replacing a focused map control when its selection already matches.
    const pressed =
      document.querySelector('.legend-row[aria-pressed="true"]')?.dataset
        .category || "all";
    if (pressed !== state.mapCategory)
      document.getElementById("spatial-overview").innerHTML = spatialOverview();
  }
  document.querySelectorAll(".finding, .research-finding, .brief-paragraph").forEach((e) => {
    e.classList.toggle("selected", e.id === id);
    e.querySelector(".finding-select, [data-action=evidence]")?.setAttribute(
      "aria-pressed",
      String(e.id === id),
    );
  });
  const pane = document.getElementById("inspector");
  if (pane) {
    pane.innerHTML = evidence(id);
    pane.scrollTop = 0;
  }
  if (matchMedia("(max-width:1120px)").matches) {
    const title =
      selectedWebFinding(id)?.finding.title ||
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
function positionRailTooltip(event) {
  const item = event.target.closest(".rail-collapsed .rail-item");
  const tooltip = item?.querySelector(".rail-tooltip");
  if (tooltip) {
    const bounds = item.getBoundingClientRect();
    tooltip.style.top = `${bounds.top + bounds.height / 2}px`;
  }
}
document.addEventListener("pointerover", positionRailTooltip);
document.addEventListener("focusin", positionRailTooltip);
document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-action]");
  if (!b || b.disabled) return;
  const a = b.dataset.action;
  if (a === "contact" && showcase) { location.href = `mailto:${showcase.contactEmail}`; return; }
  if (showcase && ["new", "start", "generate", "delete-report", "confirm-delete", "export", "download", "research-again", "confirm", "locate"].includes(a)) return;
  if (a === "toggle-sidebar") toggleSidebar();
  else if (a === "delete-report") {
    const run = state.runs.find((r) => r.id === b.dataset.id);
    if (!run) return;
    openDialog(
      "Delete saved report?",
      `<p>${esc(run.address)}</p><p class="caption">This removes the saved report and its sources from this app. Original imported files, if any, remain unchanged.</p><p id="delete-error" class="error" role="alert"></p><div class="actions">${btn("Cancel", "close-dialog", "secondary")}${btn("Delete report", "confirm-delete", "primary", `data-id="${esc(run.id)}"`)}</div>`,
    );
  } else if (a === "confirm-delete") deleteReport(b.dataset.id, b);
  else if (a === "home" || a === "saved") go(a);
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
    state.mobileSidebarOpen = false;
    state.nav = b.dataset.nav;
    state.mapCategory = "all";
    state.selected = null;
    render();
    if (matchMedia("(max-width:720px)").matches) {
      const heading = main.querySelector(".panel-title, .report-heading h1");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
    } else
      main
        .querySelector(`[data-nav="${state.nav}"]`)
        ?.focus({ preventScroll: true });
  } else if (a === "research-topic" || a === "read-research") {
    openResearch(b.dataset.topic);
  } else if (a === "filter") {
    state.filter = b.dataset.filter;
    state.mapCategory = "all";
    state.selected = null;
    render();
    main
      .querySelector(`[data-filter="${state.filter}"]`)
      ?.focus({ preventScroll: true });
  } else if (a === "map-category") {
    state.mapCategory = b.dataset.category;
    document.getElementById("spatial-overview").innerHTML = spatialOverview();
    const trigger =
      document.querySelector(`[data-category="${state.mapCategory}"]`) ||
      document.querySelector("[data-category]");
    const category = mappedCategories().find((c) => c.id === state.mapCategory);
    state.selected = category?.evidenceId || null;
    const pane = document.getElementById("inspector");
    pane.innerHTML = evidence(state.selected);
    pane.scrollTop = 0;
    returnFocus = trigger;
    trigger?.focus({ preventScroll: true });
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
    state.mapCategory = "all";
    if (document.getElementById("spatial-overview"))
      document.getElementById("spatial-overview").innerHTML = spatialOverview();
    document.getElementById("inspector").innerHTML = evidence(null);
    document.querySelectorAll(".finding, .research-finding, .brief-paragraph").forEach((x) => {
      x.classList.remove("selected");
      x.querySelector(".finding-select, [data-action=evidence]")?.setAttribute("aria-pressed", "false");
    });
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
    state.page === "report" &&
    !dialog.open &&
    state.mobileSidebarOpen &&
    matchMedia("(max-width:720px)").matches
  ) {
    if (e.key === "Escape") {
      e.preventDefault();
      toggleSidebar();
      return;
    }
    if (e.key === "Tab") {
      const items = [...document.querySelectorAll("#report-sidebar button")];
      const first = items[0],
        last = items.at(-1);
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    return;
  }
  if (
    e.key === "Escape" &&
    !dialog.open &&
    state.page === "report" &&
    state.selected
  )
    document.querySelector('[data-action="close-evidence"]')?.click();
});
matchMedia("(max-width:720px)").addEventListener("change", () => {
  state.mobileSidebarOpen = false;
  if (state.page === "report") {
    const shell = document.querySelector(".report-shell");
    if (shell) {
      shell.className = sidebarShellClass();
      document.getElementById("report-sidebar").outerHTML = reportSidebar();
      syncSidebar();
    }
  }
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
