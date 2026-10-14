# Local Evidence Bench API

Run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/surreal-estate app --port 8765 --data-dir exports/web-app
```

Open `http://127.0.0.1:8765`. One process per data directory. The application is
loopback-only; this API is not a multi-user deployment or authentication system.
Static assets need no JavaScript build step. IBM Plex Sans is embedded in the CSS
copied from the approved prototype; there is no runtime font CDN dependency.

All responses are JSON unless noted. Error responses have `{ "error": "…" }`.
Requests must use the application's loopback Host. POSTs require the CSRF token
returned by `GET /api/runs` in `X-CSRF-Token`; cross-origin writes are rejected.
Responses are `no-store`. POST bodies are limited to 8 KiB.

| Method/path | Contract |
| --- | --- |
| `GET /api/capabilities` | `{apis:{available:true},web:{available:boolean}}`. Checks valid local configuration and whether the configured Ollama model is installed. Does not call paid generation or guarantee downstream service availability. |
| `POST /api/geocode` | `{address, geography?}` → `{candidates:[{confirmation,address,latitude,longitude}]}`. Address 5–200 characters; geography 3–120, defaults to Pittsburgh, Pennsylvania. Uses Census, returns at most 20 candidates. Empty array means no match; upstream failure is 502. |
| `POST /api/runs` | `{address,geography?,confirmation,channels,topics?,request_id?,parcel_id?}` → 202 run object. `channels`: nonempty subset of `apis`, `web`; `topics`: `neighborhood_discussion`, `restaurant_reviews`. Web requires at least one topic. |
| `GET /api/runs` | `{runs:[…],csrf}` sorted newest first. Includes completed, running, interrupted and imported reports. |
| `GET /api/runs/{id}` | Run state, address, geography, selected channels/topics, created date, partial flag when complete, message, elapsed seconds, and `progress:{steps:[{id,label,state}],detail,sources_checked}`. States: waiting, active, done, stopped, skipped. No estimated percentage. |
| `GET /reports/{id}/dashboard` | The application shell opening that report. Hash routes support refresh and browser back/forward. |
| `GET /reports/{id}/bench.json` | Version 1.0 display projection: case, demo, findings, evidence, coverage, web. Findings reference original evidence IDs and web indices. Model text is preserved, with sanitized `rendered_html` supplied separately. |
| `GET /reports/{id}/result.json` | Existing complete `FrontendResponse` 1.0. No information is removed because the interface does not show it. |
| `GET /reports/{id}/source.json` | Complete saved `DevelopmentSnapshot` 1.0, suitable for download and reopening with the existing CLI. |

Confirmation tokens last 30 minutes, remain in server memory, and bind to the
submitted address and geography. Generation uses the server-held resolved address
and Census coordinates, never client-supplied coordinates. Restart/expiration
requires confirming the address again. The confirmed location is also recorded in
new job metadata. Optional parcel IDs are validated by the existing adapter.

`request_id` is an 8–100 character alphanumeric/hyphen client identifier. The app
creates a UUID and keeps it across retries. Replaying identical input returns the
original job even after restart or completion. Reusing it with different input
returns 409. The server also allows only one active run at a time. Invalid input
returns 400, stale confirmation/active-run conflicts 409, missing records 404,
invalid Host/CSRF/Origin 403, and persistence errors 500.

## Storage and compatibility

No SQL migration is required. The separate retention-filtered SQLite store is
unchanged. Local job metadata gains optional `request_id`, `request_fingerprint`,
`location`, and `imported` fields. Missing fields in older jobs remain supported.
Jobs and new research snapshots use temporary-file replacement. An interrupted
run becomes failed at startup and retains its saved selections.

At startup the app validates standalone development snapshots in its data
directory. The default `exports/web-app` directory additionally imports valid
snapshots from `exports`. Import adds a report copy and job entry, deduplicating by
the original report ID; originals are never overwritten. Malformed snapshots are
ignored. To import elsewhere, copy a snapshot into the configured data directory
and restart. Existing metadata defaults normalize older source records; older OSM
observations display without requiring new area-summary fields.

The display mapper groups related topics, retains underlying evidence and
coverage, and does not infer web conflicts, property risk, travel times, or missing
records. Provider HTML is only displayed in a sandboxed iframe. Model Markdown
disables active HTML, unsafe links and remote images. The original web responses,
source slots (including missing URLs), support indices and Search Suggestions are
preserved. The frontend stores only setup drafts/request IDs in session storage.

## Configuration and limits

Public sources require no API key. Optional web research requires `GEMINI_API_KEY`,
the configured `GEMINI_MODEL`, and local Ollama with `OLLAMA_MODEL` (defaults to
`nemotron-3-nano:4b`) at `OLLAMA_BASE_URL` (defaults to loopback port 11434).
The CLI reads `.env` from the working directory; exported values take precedence.
Web research can incur provider charges. Unavailable web choices are disabled;
the app provides a readiness recheck. Provider failures remain coverage gaps.

Census resolves US addresses. Property/permit coverage is geographically bounded;
FEMA/public Overpass availability varies. There are no travel-time, school-quality,
or independently verified web-conflict providers. Older snapshots may lack parcel
candidate IDs; the interface preserves that missing data rather than inventing it.

Tests: `.venv/bin/pytest -q`. See `interface-implementation.md` for screen mapping.

Browser checks use Playwright as optional test tooling, not an application
dependency. With `playwright` installed and Chromium available, run:

```sh
APP_URL=http://127.0.0.1:8765 node scripts/verify_webapp_offline.cjs
APP_URL=http://127.0.0.1:8765 node scripts/verify_webapp.cjs --live
```

`NODE_PATH` can point to an external test installation's `node_modules`;
`CHROMIUM_PATH` optionally supplies its Chromium executable. The offline browser
check intercepts API requests with test-only fixtures and makes no provider calls.
The explicitly opted-in live check generates a real report, selecting configured
web channels (which can incur charges). Both save desktop/mobile, light/dark
screenshots under `.impeccable/review/bench`.

Explicit web topic selections are completed before the policy gate if the model
planner omits a supported topic and the existing call budget permits it. Each
query still passes normal address, geography, topic and budget validation. A failed
web query records its own coverage error and allows the next selected topic to run.
