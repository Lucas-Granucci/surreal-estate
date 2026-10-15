# Evidence Bench webapp

Visual authority: the user-approved `design/SurrealEstate.html`. The user explicitly selected its Evidence Bench, graphite palette, IBM Plex Sans, system-controlled light/dark themes, landing composition, conventional research choices and concise progressive disclosure. It supersedes the earlier Pocket-atlas direction. Shipped implementation: `surreal_estate/webapp/static/{index.html,app.css,app.js}`, with data normalization in `display.py` and API behavior in `server.py`.

## Direction contract

THESIS: Make an address understandable through concise findings with evidence close at hand.
OWN-WORLD: Evidence Bench. Graphite actions; light and dark neutral surfaces selected by the system; embedded IBM Plex Sans; borders and tonal layering; restrained preview/dialog shadows. No theme toggle.
STORY: Landing → address → confirm actual match → conventional research checkboxes → actual milestone progress → findings/unresolved → source inspection and research scope. Saved reports remain accessible.
FIRST VIEWPORT: Preserve the approved large left-aligned landing headline and two actions above the framed report preview. Report view uses address context, view navigation, concise findings and an adjacent evidence inspector when space permits.
FORM: Implement the approved HTML reference directly. Keep the approved spacing, type hierarchy, component shapes and responsive arrangement. Bind every preview, finding and progress state to available data; use honest empty/loading/error states when it is absent.

## Layout and interaction

The report uses a collapsible navigation sidebar / findings / evidence layout (232px / flexible / 340px), widening at 1500px. The sidebar contains branding at the top and global report actions at the bottom; the report has no app top header. Collapsing leaves a 64px icon rail; the top brand mark becomes the expand control on hover or keyboard focus. Branding uses primary text, aligned with the navigation icon centreline. At 1120px and below evidence opens in a dialog. At 720px and below the sidebar opens as a modal drawer from a compact menu button, preview content stacks, filters become two columns and evidence uses a full-screen dialog. The landing hero, preview and value rows retain separate widths. See DESIGN.md for exact tokens and dimensions.

A finding selection highlights its row and opens its actual evidence. Qualifiers remain beside findings; records, links and raw evidence use concise disclosures. Findings, Unresolved, Sources and Research scope are separate report views. Public records/community mapping and model summaries/AI reviews stay distinguishable. No invented distance, travel time, property claim or progress percentage is permitted. Permits do not verify active work; geocoding provides an estimated street point.

## State coverage

Address input, geocoding, no match, candidate confirmation, invalid input and retained correction flow; enabled/disabled web research with availability recheck; waiting/active/done/stopped/skipped milestones; interrupted generation and reconnect/retry; loading/missing report; saved-report search and empty results; selected/unselected findings and filters; available/empty/blocked/unavailable/error coverage; desktop inspector and mobile dialog. The landing preview reads actual saved results or shows an empty preview.

## Implementation boundaries

The prototype’s fixture content is not product data. The backend exposes a display projection without removing original source data; complete snapshots remain downloadable. The operational contract is documented in `docs/webapp-api.md`, and screen/capability mapping in `docs/interface-implementation.md`. PRODUCT.md remains unchanged. This brief owns the surface composition; DESIGN.md owns the reusable visual system.

## Quality bar

Match the approved composition in both system themes; keep controls legible at mobile widths; retain keyboard focus and reduced-motion support; never hide factual qualifications merely to shorten the view. Existing uppercase metadata labels and text-symbol status/close controls are inherited implementation details, not new reusable design rules.

The research flow hides Saved reports. Progress updates in place without replaying
entry animation or replacing unchanged status nodes and spinners.


## Tavily web research (2026-10-15)

New runs use Tavily Search exclusively, local Nemotron planning and targeted review,
and Gemini API writing of the final brief without search/grounding tools.
`report.result.research` / bench `research` carry source-linked
findings and exact original passage references. Web research has a dedicated
main-column reader with topic tabs; the inspector carries selected source excerpts,
publication/retrieval context and original links. The same evidence opens in the
mobile dialog. New findings survive snapshots and durable export; saved Gemini
responses remain readable separately. See `docs/tavily-research.md` for setup,
budgets, failure behavior and the storage contract.

The main reader prioritizes Gemini's thematic prose, with numbered source links at
paragraph ends and an evidence action for original cited passages. The inspector
groups passages from the same source. Writer failures retain extraction notes and
sources, with an explicit limitation; older reports do not trigger paid rewriting.

Web research is a dedicated sidebar destination. Findings has compact topic previews
with a first-sentence excerpt, coverage status and a direct Read brief action. It has
no Web research filter, and web topics are excluded from the adjacent records status
table to avoid duplicate entries. Older reports link to available research notes.
