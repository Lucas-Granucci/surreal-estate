# Architecture

SurrealEstate combines fixed public-data adapters with bounded web research.
Public sources run independently of the model planner. Completed evidence remains
available when another provider fails.

## Execution

1. Reuse the user's confirmed Census match, or perform a bounded Census lookup.
2. Fetch mapped surroundings, then county assessments, parcel resolution, permits
   and same-street closures. Flood-map adapters are removed.
3. Validate the local Nemotron plan against selected channels, topics and geography.
4. Resolve the Pittsburgh neighborhood from the confirmed point when available.
5. Tavily retrieves sources for neighborhood/street-aware discovery queries.
6. Nemotron extracts notes with exact passage references and optionally requests a
   targeted check. Unrelated discussion results and unsupported findings are omitted.
7. Gemini writes a cited thematic brief from supplied material without search tools.
8. Validate provenance, assemble the report, and save the display snapshot.

Tavily is the only live search provider. The old Gemini grounded-search client and
same-provider grounded re-check agent are deleted. Historical saved web response
models/rendering remain for read-only compatibility. Synthetic search fixtures
support fully offline evaluation and never imply live evidence.

## Source boundaries

Provider policy defines extraction, retention and approved public-data hosts.
Tavily evidence contains returned passages/page content and original URLs. Structured
adapters restrict fields and geography and retain provider attribution. No arbitrary
model-generated URL becomes a backend fetch target. Local Ollama must use loopback.

Gemini writing receives bounded, policy-approved evidence and unverified local
notes. It returns structured paragraphs with source references. The backend attaches
original excerpts, rejects unknown refs and incomplete responses, and permits one
format-repair attempt. Source support is not independent factual verification.

## Resilience and budgets

A run permits two web topics, six Tavily searches, eight local model calls, four
Gemini writing attempts including repairs, and 24 public API dispatches. The shared
deadline is 300 seconds. Every HTTP dispatch consumes its corresponding budget.
Public responses are capped at 2 MB. Model requests have a 60-second ceiling;
public requests are normally 12 seconds, with bounded longer windows for Overpass
and the neighborhood boundary query.

Transient public gateway/transport failures receive one retry. Overpass can use a
second approved endpoint. Admission rejection respects the operator's pause.
Validated map responses are cached in memory and local source-cache files: 24-hour
normal reuse, with an explicitly dated fallback up to seven days old after refresh
failure. Expired, incomplete or malformed responses are not represented as new data.
WPRDC catalog resolution is cached for five minutes. Source outages are coverage
limitations and never evidence that records or features do not exist.

## Storage and display

`RunReport.result` holds evidence, observations, coverage and research. Each
`WebResearch` may contain a `ResearchBrief`, paragraph citations, extraction notes,
queries, limitations and synthesis status. Evidence IDs must exist in the report.
SQLite and durable export filter retention and rebuild claims; briefs are omitted
if their cited evidence cannot be retained. Debug events and credentials are not
persisted in the report.

The Evidence Bench presents records and a map on Findings, compact web previews,
and full briefs on the Web research page. Inspectors show original cited passages.
The bench projection hides retired flood entries in historical snapshots while
preserving original snapshot files. Cached maps visibly show their retrieval date.

The local HTTP server binds to loopback, validates host/origin and CSRF for mutations,
saves completed reports, and preserves deletion tombstones across restart.
