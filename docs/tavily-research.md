# Tavily research

New live research uses Tavily Search and local Ollama/Nemotron for discovery and research
processing, then Gemini for the final cited brief, with no Gemini search/grounding tools. The old Gemini search client and grounded re-check agent are deleted. Historical
saved responses retain read-only display compatibility.

## Setup

Create/sign into https://app.tavily.com, complete its account flow, and obtain a key.
Put `TAVILY_API_KEY=...` in the project's `.env`, alongside `OLLAMA_BASE_URL` and
`OLLAMA_MODEL`. Use `TAVILY_SEARCH_DEPTH=basic` or `advanced`; Basic is the default.
The application never prints the token. Debug payloads redact registered secrets,
including the Tavily token. `.env` is ignored by Git. Restart a running app after
changing configuration; exported environment variables take precedence over `.env`.

The capability check verifies configuration and the local model, without a paid
Tavily call. It cannot establish that the key has valid provider access. HTTP 401,
429, missing content, source/date limitations and interrupted synthesis are reported
as research gaps. The bounded live smoke is `scripts/smoke_tavily.py` (three searches
maximum, one topic, no credentials or response bodies in output).

## Pipeline and budgets

Nemotron's existing property planner selects requested topics. For each topic a
local SearchTasks role plans at most two complementary queries. Every query is
anchored to the case geography. Tavily Search returns up to five URLs, source
passages and optional Markdown page content; `include_answer=false` prevents
provider-generated answers from being confused with evidence. Sources are deduplicated
by URL, kept within a bounded context and labeled as page content, search passage or
a combination. Relevant search passages precede page text to avoid navigation-heavy
content dominating the local model context. Publication windows are assessed locally
instead of filtering out useful undated opinions. Literal numeric details must occur
in cited excerpts; missing addresses, ratings and dates cannot be filled from the case.

Nemotron's ResearchDraft role returns findings, numbered passage references, limitations,
location relevance, follow-up questions and one optional factual check query. The generation schema constrains reference IDs to supplied passages. The backend
attaches original excerpt text and checks citation/source membership locally. Unsupported
findings are omitted; source material remains inspectable if synthesis fails.
The optional third search targets a material uncertainty. The final local pass
reconsiders the brief against original and additional evidence, incorporating
corrections and preserving attributed opinions. Failed checks retain the first brief.

Default budget: two topics, six Tavily searches, eight local model calls, 300-second
run deadline, 60 seconds per request. Advanced searches cost two credits; Basic costs
one. Per-call returned usage is aggregated; failed calls have unknown billing.
No automatic provider fallback or Gemini grounding is enabled.

## Data and display

`ChannelResult.research` contains WebResearch briefs, WebFinding entries and exact
WebCitation excerpts referencing ordinary Evidence IDs. Evidence details retain a
bounded source content copy and provenance. Missing publication dates are not replaced
with retrieval dates. The existing Observation schema remains for structured records.
Report validation rejects findings whose cited sources are absent.

The bench projection transports new briefs under `research` while preserving
legacy `web` responses. Web research navigation and topic tabs open the main-column
reader. Finding selection opens only that finding's source excerpts, dates and
retrieval context. Facts/opinions and AI review assessments have visible labels.
Limits, follow-up questions, source list, queries and credit usage are separate
reading sections/disclosures. Mobile uses the existing accessible evidence dialog.

New Tavily findings/evidence survive snapshots, SQLite and durable export. The retired Gemini search policy is removed. Tavily material is processable under the configured
provider policy; this does not confer universal rights to publisher content or
promise complete Reddit/Yelp access. No scraping of Gemini-returned links occurs.

## Verification

Tests cover provider-answer exclusion, private URL filtering, token redaction,
unsupported quote rejection, undated opinions, corrections, partial failure,
search-call bounds, provenance validation and snapshot/export/display round trips.


## Final cited brief writing

Set `GEMINI_API_KEY` to the existing Gemini key. `GEMINI_SYNTHESIS_MODEL` defaults to
`gemini-3.8-flash`, falling back to `GEMINI_MODEL` when no synthesis override is set.
The dedicated GeminiBriefWriter never enables tools, Google Search or URL Context.
It receives only policy-approved source material, research scope and unverified local
notes, and returns structured overview/sections with paragraph-level source references.
The backend resolves references to original passages and rejects unknown refs,
provider grounding metadata, truncated responses and model-written arbitrary links.

`WebResearch.brief` holds the narrative and its citations; `summary` contains the
brief overview for consumers. `synthesis_status` distinguishes complete, error and
not-run (older reports). Up to four independently budgeted final-writing calls are permitted:
one per topic plus one format-repair attempt per topic, within the existing run deadline.
Invalid structure or citation constraints trigger the bounded repair; network errors do not.
If writing fails, sources and local extraction notes remain available
with an explicit limitation. Final writing is synthesis, not a new factual verification.

The main reader puts the brief first. Numbered source links appear at paragraph ends,
with an evidence action for the exact cited passages and a source list below. Briefs
survive snapshots/exports; a durable export drops a brief if its citations cannot be
retained. Old reports remain readable without triggering paid writing automatically.

Findings shows compact web-topic previews and coverage status, with links that open
the corresponding topic in the Web research sidebar page. Full briefs live on that
page; Findings has no separate Web research filter or duplicate web-status rows.

To create a new brief from an existing Tavily snapshot without new web searches:

```sh
.venv/bin/python scripts/synthesize_brief.py INPUT.json --output exports/brief.json
```

This preserves the original and creates a new report ID. It does not process saved
Gemini grounded answers or send them to the writer.

## Source recovery and local search context

Public requests retry transient gateway/transport errors once, with every dispatch
counted against a 24-call API budget. The map runs early, uses documented form-encoded
Overpass QL, retries a transient primary failure, then tries the documented Private.coffee
mirror. Admission rejections respect a 30-second pause. Both public servers can still
be unavailable. Successful map responses are cached for 24 hours in memory and in
local `source-cache` files; an unavailable refresh can fall back to saved data up to seven days old, with a visible date and refresh-failure notice; cache reuse preserves the retrieval timestamp and is
identified in coverage. WPRDC catalogs are cached in memory for five minutes.
Permanent connection failures appear as unavailable coverage, never absent features.

An official Pittsburgh neighborhood polygon query supplies search context from the
confirmed/geocoded point. If unavailable, street context is retained. The former
citywide discussion-query override is removed. Discussion discovery uses neighborhood
and street queries; unrelated sources are excluded when the neighborhood is resolved.
Dining discovery retains the exact address and street. Gemini writes only the current
topic, omits unidentified restaurant reviews, and distinguishes historical plans and
temporary daily closing indicators from current operations. Narrow deterministic
checks reject unsupported daily-service and permanent-closure statements.
