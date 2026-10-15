# Surreal Estate

Small Python/asyncio property-research backend. Pittsburgh is the initial geography.
Structured-data runs use a fixed set of public APIs and need no model or API keys.
With `--web`, local Ollama `nemotron-3-nano:4b` plans typed Channel C calls.
No agent framework, crawler, autonomous shell tools, or public deployment.

## Local web app

Start the app once, then enter addresses and choose research channels in the browser:

```sh
.venv/bin/surreal-estate app
# Open http://127.0.0.1:8765
```

The approved Evidence Bench interface starts with an address, a real Census match,
and three research choices: public records & nearby places, local discussions,
and dining research. It uses the approved graphite palette, embedded IBM Plex Sans,
and system-controlled light/dark themes. Desktop evidence appears alongside the
findings; mobile evidence opens in a full-screen dialog. Findings, unresolved
research, sources, scope and full JSON export remain one step away.

Address input and channel choices survive refresh in the browser session.
Confirmation is checked again after reload, expiration or server restart. The
pipeline uses the server-held resolved address and coordinates consistently.
Street-only inputs default to Pittsburgh; include city, state or ZIP for other US
addresses. Coordinates are street-range estimates, not verified building points.

Public sources need no keys. Optional web research uses the existing Gemini/Ollama
configuration; unavailable choices are disabled. Selected topics control actual
research. Progress comes from backend execution stages, without estimated
percentages. Repeated submissions with the same request ID return the same run.
Failed and partial research retain available results and expose recovery actions.

Reports are saved locally under `exports/web-app` and survive restart. Existing
saved reports still open; valid older standalone snapshots are imported additively
without changing their original files. `--data-dir PATH` changes the directory;
`--port 9000` changes the port. Keep one app process per directory. The separate
policy-filtered SQLite/durable export path is unchanged; no SQL migration is needed.

Provider records, model text, citations, source slots and Search Suggestions remain
available. Missing parcel IDs, unavailable flood data and unverified model accounts
are never replaced with prototype findings. Candidate parcel records, when returned,
remain visible in evidence; explicit parcel research remains supported by the API
and CLI (`research --address '...' --parcel-id ID`).

The server is loopback-only and uses same-origin CSRF protection. The original
`research`, `demo`, and `view` commands remain available. See the
[screen implementation map](docs/interface-implementation.md) and
[API, storage compatibility and configuration contracts](docs/webapp-api.md).

## Run

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/surreal-estate demo --db demo.db
.venv/bin/pytest -q
```

The demo runs entirely offline with synthetic evidence; it makes no claims about
its Pittsburgh fixture address. The demo SQLite database can be discarded.

Default live structured research (no Ollama or API key required):

```sh
.venv/bin/surreal-estate research --address '414 Grant Street, Pittsburgh, PA 15219' --db research.db
```

Add Gemini grounding explicitly (requires local Ollama with `nemotron-3-nano:4b`). The default is `gemini-3.8-flash` with
Google Search enabled. This project uses a billing-enabled Gemini account;
model tokens and search usage can incur charges. See [current pricing](https://ai.google.dev/gemini-api/docs/pricing).
Older 2.5 models may appear in the model catalog while rejecting new-user requests.

```sh
export GEMINI_API_KEY='your-key'
export GEMINI_MODEL=gemini-3.8-flash
.venv/bin/surreal-estate research --address '414 Grant Street, Pittsburgh, PA 15219' --web --db research.db
```

`--web` prints a random, loopback-only URL after research completes. Open it to see
Gemini's separate answer, links, and Search Suggestions. The CLI also prints a
`Frontend JSON` URL containing the main report and both web responses with their
source links, citation mappings and Search Suggestions. This response is for
same-application user display and includes live web content. See
[the frontend response contract](docs/frontend-response.md).
Ctrl-C ends the viewer; results also expire after 15 minutes, or when the frontend
acknowledges viewing with `POST /<token>/release`.
Live responses never enter SQLite or terminal output. During development, CLI runs
also save `exports/<run-id>.json`, including the main report, original Gemini answer,
re-check, source chunks, supports and Search Suggestions. The CLI prints the filename
before opening the viewer. Each run gets its own file; failed runs are saved too.
Use `--no-save-json` to disable this development snapshot. `exports/` is Git-ignored.
These files persist after the viewer closes; delete them when finished debugging.
Snapshots are labeled `development_debug` / `development_file` and exclude debug
request/response payloads. Model text is preserved exactly in JSON and rendered
as Markdown in the viewer (headings, lists, tables, links, emphasis and code).
The viewer
sets `Cache-Control: no-store`, disables access logs, and sandboxes provider HTML.
It is a development viewer, not a reviewed production display implementation.
No live Gemini call occurs unless `--web` is supplied. The CLI automatically loads
`.env` from the current working directory; run commands from the project root to
use its `.env`. See `.env.example` for variable names. Exported environment variables
take precedence, including empty values; use `unset GEMINI_API_KEY` to let the file
supply the key if your shell already defines it. `.env` is ignored by Git.

If `--web` reports a missing key, add `GEMINI_API_KEY=your-key` to `.env`, or set it
in the same zsh terminal without putting its value in shell history:

```zsh
read -rs 'GEMINI_API_KEY?Paste Gemini API key: '
printf '\n'
export GEMINI_API_KEY
export GEMINI_MODEL=gemini-3.8-flash
```

Configuration errors name the setting without showing its value. Provider errors
report the HTTP status and a static troubleshooting hint; raw response bodies and
request headers are not logged. Redacted JSON responses are available only in the in-memory dashboard debugger. A 429 indicates a rate/quota limit, not necessarily
a requirement to enable billing.


## Default structured-data sources

Every live `research` run includes these sources, with or without `--web`:

| Source | What is included | Setup |
| --- | --- | --- |
| Census Geocoder | Normalized address, interpolated coordinates, county and municipal geography | None |
| Allegheny County assessments / WPRDC | Automatically resolved parcel, recorded building attributes, assessed values and sale fields | None |
| Pittsburgh PLI / WPRDC | Up to 50 latest permits on the uniquely matched parcel, including Building & Development Applications | None |
| FEMA NFHL | Flood-zone intersection and map-panel effective dates at the interpolated address point | None |
| OpenStreetMap / Overpass | Four concise area summaries: schools, grocery stores, transit stops and pharmacies within a 1 km query | None |
| Pittsburgh DOMI / WPRDC | Same-street closure segments within 1 km; records not ended as of the case date, starting no more than 90 days ahead | None |

**No new API keys or `.env` entries are needed.** Gemini credentials remain optional
and apply only to `--web`. `demo` stays offline and synthetic; `view` only reopens
saved data. The structured baseline runs before optional model planning, so model
omissions or planning errors cannot suppress it.

WPRDC resource IDs are resolved from current catalog entries on every run. County
and city boundaries come from Census geographic identifiers, not postal city names.
Assessment matching starts with exact house number/street/ZIP candidates without
units or fractions. Multiple parcel IDs are ranked using county address-point
parcel links and intersecting parcel boundaries. Ties or unavailable GIS use a
stable normalized parcel-ID fallback, explicitly labeled as uncertain. Candidate
IDs, GIS checks and the selection reason are retained with the assessment and
permits. At most two additional GIS calls are made, preserving the downstream
research budget. No candidate still means no parcel can be selected. PLI lookup uses
the selected parcel, starts with the feed's June 2019 coverage, and excludes plumbing.
Closures search the matched street only, not every nearby street; missing end dates
and active flags remain uncertain. No returned records is not proof of absence.

Evidence JSON includes selected structured fields, record/resource IDs, publication
and record dates when supplied, attribution, and matching methods. Owner names and
mailing addresses are not requested. These public records are eligible for the
existing durable export/SQLite path; OSM attribution and ODbL licensing are retained.
Assessments describe recorded values, not current appraisals. FEMA uses an
interpolated point, not parcel/building boundaries. OSM distances are straight-line
point/center distances, not walking times or confirmed entrances.

Calls are sequential and bounded: 12 API calls per run (10 on the full successful
path), 12 seconds per request (35 seconds for Overpass queue/execution time) and 2 MB
per response, with no automatic retries. Empty, blocked,
truncated and failed sources appear individually in coverage; completed sources
survive later failures. The shared 180-second deadline still applies.

The OSM adapter uses `https://overpass-api.de/api/interpreter` with a raw
Overpass QL POST body and a User-Agent identifying this project's repository.
This replaces the failing Private.coffee endpoint. Live verification returned
usable objects around the sample Pittsburgh address. Results are now summarized
into exactly four categories, not one finding per place. Each category has its own
50-object cap; a dense transit category cannot crowd out schools or groceries.
Successful summaries are marked complete even when a category reaches its cap;
limit metadata remains available in the data. Supporting names, links and tags
remain in expandable details. Restaurants, cafés,
parks and clinics are excluded by default. Counts describe mapped features, not
verified distinct facilities; capped counts are lower bounds, and the closest
returned point/center need not be the area's nearest amenity. School attendance
zones/quality and transit service frequency are not inferred.
Each record includes the query endpoint in its provenance. No API key is needed.
Public Overpass availability varies; errors remain isolated, with no immediate
retries on throttling. Run research again to replace a previously failed snapshot. A bounded live check is available:

```sh
.venv/bin/python scripts/smoke_sources.py --address '1430 McKenna Ave, Pittsburgh, PA 15205'
```

It calls no models, saves no output files, and reports source status and counts.

## Structured downstream export

CLI runs save a development display snapshot to `exports/<run-id>.json` by default.
Use `--export exports/property.json` to choose the filename for that full snapshot:

```sh
.venv/bin/surreal-estate research \
  --address '414 Grant Street, Pittsburgh, PA 15219' \
  --web --viewer --export exports/property.json
```

The development JSON contains `schema_version`, `purpose`, `retention`, `report`
and `web`. `web[]` holds both original search and re-check entries, with full text,
source URL/title chunks, supported segments and citation mappings, search queries,
Search Suggestions and truncation status. It is pretty-printed with two-space
indentation. An explicit filename is overwritten on subsequent runs; default
run-ID filenames preserve each run. Consumers can validate with
`DevelopmentSnapshot.model_validate_json(...)` from `surreal_estate.synthesis.frontend`.
The dashboard's **View full JSON** link opens the same data in an indented,
scrollable section; `/result.json` is also pretty-printed. Nemotron's JSON output
is indented in the debug inspector. Model summaries remain Markdown-rendered.

For policy-filtered processing exports, use `--durable-export PATH`. This writes
`ResearchExport` (including `omissions`) and excludes live grounded content.
`--db research.db` applies the same retention filter to SQLite. These explicit
durable paths remain separate from the full development snapshots. Debug request
and response payloads are excluded from both JSON contracts. The offline
`demo --export exports/demo.json` exercises snapshot saving with synthetic evidence.

## What's implemented

- Pydantic channel contracts and provenance references; SQLAlchemy/SQLite run store.
- Local Nemotron research planner, separate fact-check planner, and fixture-only extractor.
- Typed query policy, call budgets, deadlines, deterministic sequential runner,
  execution trace, explicit error/empty/not-implemented coverage.
- Census geography lookup, county assessments, city PLI permits and DOMI closures, FEMA map context, and OSM amenities; explicit matching, attribution and bounded public requests.
- Gemini grounded client preserving chunk/support indexing and Search Suggestions;
  isolated in-memory display, no extraction or persistence of live results.
- Conservative fixture verifier: same-support text/date/geography, citation existence,
  single-URL source flag; deterministic dossier synthesis and offline tests.

## Deliberately next

Audience (private buyer vs agent tool vs public reports) is not yet decided.
Next: ACS, EPA, API caching,
PDF/page citations, photo questions, assessor discrepancies, semantic conflict
analysis, and labeled-property evaluation are not yet implemented.

See [architecture and decisions](docs/architecture.md) for boundaries and limitations.
See [proposed sources](docs/proposed-sources.md) for API, upload and open-web
integration candidates for Pittsburgh. The viewer lists each run's actual sources
at the top, grouped into Channels A/B/C, with returned and cited web links.

## SSH browser viewer and model diagnostics

Check the configured model against Google's model list without generating content:

```sh
.venv/bin/surreal-estate gemini-models
```

This loads `.env`, prints the effective model and lists models supporting
`generateContent`. It does not establish grounding support or project quota.
Google's [model availability notice](https://ai.google.dev/gemini-api/docs/deprecations#gemini-2.5-flash-models)
currently restricts 2.5 access to prior users, so the published free allowance alone
is not a guarantee of access for a new project. No automatic model substitution occurs.

On your laptop, establish a tunnel (replace `user@remote-host`):

```sh
ssh -N -L 8765:127.0.0.1:8765 user@remote-host
```

In your SSH terminal on the remote machine, run:

```sh
.venv/bin/surreal-estate research \
  --address '414 Grant Street, Pittsburgh, PA 15219' \
  --web --viewer --port 8765
```

Open the complete `http://127.0.0.1:8765/<random-token>` URL printed by the remote
command in your laptop's browser. Keep both the tunnel and research process running.
The viewer is loopback-only and remains available even when a channel fails. It
shows the plan, channel statuses, supported observations, execution trace and any
separate Gemini responses. This is a completed-run snapshot, not live streaming.
Use `demo --viewer --port 8765` to test the viewer without external calls.
If the port is in use, choose another port in both commands. `--port 0` retains
random-port behavior. Results remain in memory; no static Gemini HTML export is made.


## Dashboard debugger

Use `--web --viewer --port 8765` as above. After the run, open **Inspect prompts &
responses**. Numbered steps show:

1. **Nemotron / ResearchPlan:** actual system/user messages, request schema and
   generation options, provider response, parsed plan, timing, HTTP status.
2. **Policy gate:** case, proposed plan and budgets, allowed/blocked decision.
3. **Gemini / grounded search:** exact query specification, endpoint/model,
   prompt and `google_search` configuration, full response JSON, search queries,
   grounding chunks/supports, completion metadata and reported token usage.
4. **Nemotron / FactCheckPlan:** separate agent's checks based only on the case/topic.
5. **Fact-check policy:** model-proposed checks, required checks added by the runner,
   deduplicated effective checklist, scope validation and allowed/blocked outcome.
6. **Gemini / claim re-check:** original answer sent back to Gemini with Google Search
   to assess claims and provide citations, uncertainties and follow-up questions.

The main result section keeps the Gemini answer alongside its links and Search
Suggestions. The debug panel is a read-only run snapshot, not a live console or
an agent's inferred reasoning. It shows actual submitted/returned payloads. Open
**Full response JSON** for all provider-returned fields, including errors.

`RunContext.debug` collects redacted request/response snapshots; `RunOutcome`
passes them to the viewer separately from `RunReport`. They are never written to
SQLite, printed to the CLI, or exported to files. Authentication headers are not
captured and known API key values are redacted. Closing the process releases them.

The CLI reads `.env` at startup. Existing shell variables still take precedence:
if an old model was exported, `unset GEMINI_MODEL` before running to use `.env`.
A real end-to-end test is available (uses local Ollama, Census and paid Gemini):

```sh
.venv/bin/python scripts/smoke_research.py
```

It prints only call statuses and grounding counts, not prompts or response text.


## Fact-checking and nearby restaurant reviews

Live runs default to both `neighborhood_discussion` and `restaurant_reviews`.
Each successful displayed search is followed by a separate Nemotron-planned Gemini
re-check. The original and re-check appear in labeled panels. Successful retrieval
now says **Search completed · displayed separately**. Re-check assessments can
identify corroborated, contradicted, unresolved and opinion claims, but do not
promote any of them to independently verified dossier facts.

To test only nearby restaurant reviews:

```sh
.venv/bin/surreal-estate research \
  --address '414 Grant Street, Pittsburgh, PA 15219' \
  --topic restaurant_reviews --web --viewer --port 8765
```

The query uses Google Search for general restaurant reviews, local food publications
and Google Reviews in the immediate vicinity of the property. There is no Yelp-only
site filter and no Google Places API integration. `address_anchor` and `radius_meters`
remain in the specification for downstream use; exact radius/distance verification
is not a requirement for including a restaurant. The date window is recency context,
not an exact-date filter. Recent review themes are preferred; when snippets lack
specific themes, the model summarizes reputation from available search results.

Opinions are retained, labeled and attributed. The re-check verifies factual parts
of a statement separately and does not reject subjective perspectives for lacking
independent agreement or precise dates. Missing attribution/evidence still cannot
be replaced with invented claims. Reputation summaries remain opinion, not verified facts.

The checker plans scope/date/independence/contradiction/opinion checks plus restaurant
identity, proximity and review freshness. It never receives the original grounded
text: Python sends that text back to Gemini to refine its answer, preserving the
agreed provider-policy boundary. See the updated architecture diagram for the split.

Defaults permit up to two initial Gemini calls plus two fact-check calls and four
local model calls, within the same 180-second run deadline. A Gemini call may make
multiple internal searches. `max_queries` defaults to 3 as search guidance inside
each request; it is not a guaranteed provider-side cap. API-call limits count query
specifications, not this search guidance. Re-check failures keep the original result available.
All live grounded answers, model assessments and debug payloads remain memory-only.

The live smoke test accepts honest empty-source responses; it fails on missing
requested topics, transport/validation failures and truncation. Passing does not
mean review evidence was found or that any claim was corroborated. Unit tests exercise
supported opinion-only responses and re-check failures deterministically.

Run just the restaurant integration check with:

```sh
.venv/bin/python scripts/smoke_research.py --topic restaurant_reviews
```

## Property dashboard

Open **Open property dashboard →** from the debug dashboard, or use the
**Property dashboard** URL printed by `demo --viewer` / `research --viewer`.
The responsive report includes an overview, topic navigation, original searches
and re-checks, expandable sources and citation mappings, an evidence library,
research coverage, and the full results JSON. Source numbers preserve the provider's
original ordering, including slots with no URL. Model summaries and assessments
remain labeled separately from supported dossier observations.

Reopen a previously generated development results JSON without calling providers:

```sh
.venv/bin/surreal-estate view exports/<run-id>.json --port 8765
```

Both dashboards share the existing loopback-only, no-store viewer and its
15-minute expiration. The property dashboard links back to the debug dashboard;
saved files do not contain the original run's in-memory debug payloads.
