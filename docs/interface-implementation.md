# Approved interface implementation map

Visual authority: `design/SurrealEstate.html` (confirmed by the user; the originally
named `design/surrealestate-final.html` is absent). Keep its graphite tokens,
embedded IBM Plex Sans, responsive Evidence Bench, and system theme selection.

| Screen/action | Existing capability and data | Implementation needed |
| --- | --- | --- |
| Landing/address | Python static assets; address/geography input | Approved landing and address components; preview from saved results or an honest empty preview |
| Confirm/correct | `POST /api/geocode`: Census candidates, coordinates, expiring confirmation token | Render actual candidates; retain input on back/error; never trust client coordinates |
| Channels | `ResearchRequest.channels` (`apis`, `web`) and web `topics` | Map three approved checkboxes to channels/topics; expose configuration availability |
| Generate | `POST /api/runs`; confirmed Census match in `RunContext` | Persistent idempotency key so a repeated request cannot create a second run; save confirmed location with job |
| Progress | `GET /api/runs/{id}`; actual runner/source trace | Render milestone states, polling recovery and restart interruption; no percentages |
| Findings/unresolved | `report.result.observations`, evidence IDs, coverage; separate `web` responses | Explicit display normalization into topic rows; preserve model summaries/reviews separately; no invented summaries |
| Evidence/sources | Source metadata, selected record fields, OSM members, web chunks/supports/suggestions | Desktop inspector/mobile dialog; safe links, escaped text, sandboxed provider suggestions |
| Research scope/export | Case, plan, coverage, complete source snapshot | Scope view and complete JSON download; retain undisplayed data |
| Saved reports | Atomic `job-*.json` / `report-*.json`, loaded on restart | Search/navigation, refresh-safe route, import validated older standalone development snapshots without altering originals |

No SQL schema change is needed: the local app uses development snapshots, while
the separate policy-filtered SQLite store remains unchanged. New job metadata is
additive; missing fields in old jobs have defaults. Snapshot schema 1.0 remains
unchanged. Compatibility uses existing Pydantic defaults for source metadata and
parcel candidates; legacy OSM observations remain displayable as observations.

Underlying capability limits are not missing endpoints: county/city records have
geographic coverage restrictions; ambiguous parcels use a documented automatic ranking/fallback;
older reports may lack candidate IDs; Census supplies an estimated street point;
OSM provides mapped features and straight-line distances, not travel times;
web responses provide model accounts and source references, not independently
verified findings. Unavailable/error/empty/blocked states must stay distinct.

The implementation preserves existing uncommitted repository changes.

## Verification (13 October 2026)

- Baseline: 170 tests; final: 179 tests, including idempotency/restart, additive
  snapshot import, normalization, safe model rendering, retained source download,
  explicit topic completion and isolated web failures.
- Real browser workflow ran twice using Census and configured providers. The
  second run (`98d44839-2faa-4831-b138-8aa49290ec9b`) returned eight public-source
  evidence records and four web responses: discussions and dining, each with its
  separate AI review. Both selected web topics completed after correcting planner
  omission handling. Census, OSM and street permits completed; assessment and FEMA
  failed and dependent permits were blocked. These were displayed as partial gaps.
- Existing reports opened; saved reports survived the actual app restart. Refresh,
  source/scope/unresolved navigation, saved search and mobile Escape were exercised.
- Offline browser fixtures exercise no-match/error geocoding, unavailable web,
  submit retry, interrupted research, touch/keyboard and refreshed drafts. This
  caught and corrected the empty-geocode route guard; no fixtures ship in the app.
- Matching prototype/app captures at 1440×1000 and 390×844, both system themes.
  All major screens plus error/empty/unavailable states captured under
  `.impeccable/review/bench`; no horizontal overflow or browser JavaScript errors.
  Independent visual review found the approved layout/type/palette matched, then
  confirmed the sole Sources-button wrapping fix in both desktop themes.
- New/changed app projection/server test files pass targeted Ruff checks;
  JavaScript syntax and `git diff --check` pass.

Public providers may still fail; the checks establish truthful partial behavior,
not universal coverage. The app remains a single-user local application. Optional
web research still depends on Gemini credentials and an available local model.


The Findings view opens on Location overview. Local intelligence contains compact
agentic-research topic previews, linking to the full briefs in the Local intelligence
sidebar reader. Property & street records combines assessment, building permits and
street-closure permits. Report coverage summarizes every pipeline channel and its gaps.
The Location overview's north-up coordinate plot uses saved
OSM member centres and an estimated address point, with category filters and an
accessible location list. Missing coordinates are never synthesized. The distance
reference expands to include retained centres; it is not a property boundary.
Research status rows derive from saved coverage, link to retained evidence, and
stack on mobile. Empty searches remain complete; blocked, limited, failed,
unavailable and unknown outcomes remain distinct. Navigation uses stronger text
for the current section, without a selected background or bar.

Offline Overview regression coverage: `scripts/verify_overview.cjs` (Playwright).
It checks category/status filters, evidence access, missing coordinates, and both
system themes at desktop and mobile widths without provider requests.

Location overview owns mapped surroundings: the redundant All topics and Surroundings
filters are removed. The desktop plot is capped at 420px with compact category controls
and count/coverage information beside it. Selecting a category updates both the summary
and the evidence inspector using that category’s source ID, keeping groceries
and pharmacies distinct. Mobile stacks the summary below a 320px plot and opens
full evidence through View locations & source. Report loading starts without
selected evidence; switching views clears the category and evidence together.
Finding rows are clickable across their surface, with keyboard-accessible title
buttons, chevrons, hover/focus treatment and selected states. Disclosures remain
independently operable. Report interactions do not replay the entry animation,
and reserved scrollbar space keeps the layout stable between long and short views.

Saved reports include Delete for completed and failed runs, with confirmation,
error/retry feedback, and persistent deletion. Running research cannot be deleted.
The Location overview map section spans the full content width; the coordinate plot stays
capped at 420px and the adjacent category controls fill the remaining space.

The report page owns a collapsible sidebar instead of the app top header. Branding
and collapse controls sit above the report views; New report/View progress and
Saved reports stay in a separate bottom navigation group. Desktop collapse keeps
a 64px icon rail and retains evidence, filters and scroll. Mobile uses an overlay
drawer with focus containment, an inert report, Escape/backdrop dismissal and
focus restoration. Other pages retain the standard app header.

The brand mark shares the navigation icon centreline. In the collapsed rail it
remains at the top and becomes the expand affordance on hover or keyboard focus,
with an Expand sidebar tooltip. Branding uses the primary text color. Saved reports
is hidden during address entry, confirmation, channel selection and progress.
Progress polling patches existing status nodes rather than recreating the screen;
unchanged spinners, focus and heading position survive each update.


## Tavily web research (2026-10-15)

New runs use Tavily Search exclusively and local Nemotron planning, synthesis and
targeted review. `report.result.research` / bench `research` carry source-linked
findings and exact original passage references. Web research has a dedicated
main-column reader with topic tabs; the inspector carries selected source excerpts,
publication/retrieval context and original links. The same evidence opens in the
mobile dialog. New findings survive snapshots and durable export; saved Gemini
responses remain readable separately. See `docs/tavily-research.md` for setup,
budgets, failure behavior and the storage contract.
