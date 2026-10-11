# Transient frontend response

The frontend handoff is a typed JSON response for the requesting user's display
within this application. It includes live web-channel results. It is distinct
from `--durable-export`, which writes a retention-filtered file for durable processing.

Run the existing pipeline (development snapshots are enabled by default):

```sh
.venv/bin/surreal-estate research \
  --address '414 Grant Street, Pittsburgh, PA 15219' \
  --topic restaurant_reviews --web --viewer --port 8765
```

The CLI prints both the dashboard URL and
`http://127.0.0.1:8765/<token>/result.json`. The JSON endpoint shares the dashboard's
unguessable run token. For SSH, use the existing port-forwarding instructions.
This is a completed-run transport; the future address-submission API and frontend
are not implemented yet. No additional LLM calls are needed to build the response.

## Contract

`FrontendResponse` lives in `surreal_estate.synthesis.frontend`. Call
`build_frontend_response(outcome).model_dump(mode="json")` from a future HTTP API.
`FrontendResponse.model_json_schema()` exposes its JSON Schema. Top-level fields:

| Field | Contents |
| --- | --- |
| `schema_version` | `"1.0"` |
| `purpose` | `"user_display"` |
| `retention` | `"ephemeral"` |
| `report` | Property case, plan, typed observations/evidence/claims, coverage, demo marker; execution trace omitted |
| `web` | Original search and re-check display entries, in pipeline order |

Each `web` entry has `topic`, `stage`, `label`, and `response`:

| Response field | Contents |
| --- | --- |
| `provider` | Search provider identifier |
| `text` | Complete original model-generated summary or re-check; includes synthesized findings and fact/opinion assessments as returned |
| `chunks` | Source URL/title objects, including null-URI placeholders |
| `supports` | Supported text segments, offsets and zero-based `chunk_indices` mapping those segments to source chunks |
| `search_entry_point` | Provider Search Suggestions HTML for display alongside the answer |
| `search_queries` | Search queries returned by the provider |
| `truncated` | Whether the model response was truncated |

Citation positions are preserved, including chunks with missing URLs. Do not
filter/reindex chunks without remapping their supports. Source links and supported
segments are provenance metadata; full source pages/review bodies are not fetched.

The original entry is labeled `model_reported_summary`; the re-check is labeled
`model_assessment`. Web findings remain in `web[].response.text` and citation
supports, rather than being promoted into independently verified `report.claims`.
Show the supplied model text with its source links and Search Suggestions. Treat
provider HTML as untrusted and use a sandboxed iframe, as in the dashboard.
Debug requests/responses and credentials are not included in this handoff.

## Lifetime

During development the CLI saves `exports/<run-id>.json` before starting the viewer.
This uses `DevelopmentSnapshot`, the same fields as the frontend response with
`purpose="development_debug"` and `retention="development_file"`. Original responses
and re-checks, source chunks, supports and Search Suggestions are included. Debug
request/response payloads are excluded. Files survive viewer release/expiry and
must be deleted manually after debugging; `exports/` is Git-ignored. Pass
`--no-save-json` to return to memory-only display. This snapshot is independent
of the filtered `--durable-export` and SQLite paths. An explicit `--export PATH`
saves the full development snapshot at that filename and overwrites the file on
subsequent runs. The dashboard includes a **View full JSON** section; both that
section and the JSON endpoint are indented for inspection. The viewer renders model Markdown
without changing the saved original text; raw HTML and unsafe links are disabled.

All routes send `Cache-Control: no-store, max-age=0`. The server is loopback-only,
has no access logs and does not enable cross-origin access. The future application
should proxy this contract on its own authenticated origin.

Fetch the response with caching disabled. Keep it in frontend memory while viewing,
then clear that memory and send `POST /<token>/release` to acknowledge completion.
The backend clears its JSON/HTML buffers and closes the viewer. If no acknowledgement
arrives, it expires after 900 seconds; Ctrl-C also releases it. The CLI then exits,
releasing the original run objects. This is normal object disposal, not a guarantee
of secure erasure from RAM. Do not save the response to frontend persistent storage.

SQLite and `--durable-export` continue excluding live grounded content. Development
snapshots are the explicit local debugging exception. This display
transport does not authorize passing grounded text into another analysis model.
