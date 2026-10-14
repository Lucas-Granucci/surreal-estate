# Evidence Bench webapp

Visual authority: the user-approved `design/SurrealEstate.html`. The user explicitly selected its Evidence Bench, graphite palette, IBM Plex Sans, system-controlled light/dark themes, landing composition, conventional research choices and concise progressive disclosure. It supersedes the earlier Pocket-atlas direction. Shipped implementation: `surreal_estate/webapp/static/{index.html,app.css,app.js}`, with data normalization in `display.py` and API behavior in `server.py`.

## Direction contract

THESIS: Make an address understandable through concise findings with evidence close at hand.
OWN-WORLD: Evidence Bench. Graphite actions; light and dark neutral surfaces selected by the system; embedded IBM Plex Sans; borders and tonal layering; restrained preview/dialog shadows. No theme toggle.
STORY: Landing → address → confirm actual match → conventional research checkboxes → actual milestone progress → findings/unresolved → source inspection and research scope. Saved reports remain accessible.
FIRST VIEWPORT: Preserve the approved large left-aligned landing headline and two actions above the framed report preview. Report view uses address context, view navigation, concise findings and an adjacent evidence inspector when space permits.
FORM: Implement the approved HTML reference directly. Keep the approved spacing, type hierarchy, component shapes and responsive arrangement. Bind every preview, finding and progress state to available data; use honest empty/loading/error states when it is absent.

## Layout and interaction

The report uses navigation / findings / evidence columns (176px / flexible / 340px), widening outer columns at 1500px. At 1120px and below evidence opens in a dialog. At 720px and below the report navigation becomes a horizontally scrollable top row, preview content stacks, filters become two columns and evidence uses a full-screen dialog. The landing hero, preview and value rows retain separate widths. See DESIGN.md for exact tokens and dimensions.

A finding selection highlights its row and opens its actual evidence. Qualifiers remain beside findings; records, links and raw evidence use concise disclosures. Findings, Unresolved, Sources and Research scope are separate report views. Public records/community mapping and model summaries/AI reviews stay distinguishable. No invented distance, travel time, property claim or progress percentage is permitted. Permits do not verify active work; geocoding provides an estimated street point.

## State coverage

Address input, geocoding, no match, candidate confirmation, invalid input and retained correction flow; enabled/disabled web research with availability recheck; waiting/active/done/stopped/skipped milestones; interrupted generation and reconnect/retry; loading/missing report; saved-report search and empty results; selected/unselected findings and filters; available/empty/blocked/unavailable/error coverage; desktop inspector and mobile dialog. The landing preview reads actual saved results or shows an empty preview.

## Implementation boundaries

The prototype’s fixture content is not product data. The backend exposes a display projection without removing original source data; complete snapshots remain downloadable. The operational contract is documented in `docs/webapp-api.md`, and screen/capability mapping in `docs/interface-implementation.md`. PRODUCT.md remains unchanged. This brief owns the surface composition; DESIGN.md owns the reusable visual system.

## Quality bar

Match the approved composition in both system themes; keep controls legible at mobile widths; retain keyboard focus and reduced-motion support; never hide factual qualifications merely to shorten the view. Existing uppercase metadata labels and text-symbol status/close controls are inherited implementation details, not new reusable design rules.
