# Public showcase

The public site is a static build of the same Evidence Bench reader used by the
private application. It has a sample gallery, dated report views, citations,
source inspection, mapped locations, coverage, and a contact email. It makes no
calls to Ollama, Tavily, Gemini, or the Python backend. Links to original sources
open those sites only when selected. The private application retains generation,
saved-report management, and exports.

## Build and preview

From the repository root, with project dependencies installed:

```sh
.venv/bin/python scripts/build_showcase.py --output dist/public
.venv/bin/python -m http.server 8879 --bind 127.0.0.1 --directory dist/public
```

Open `http://127.0.0.1:8879/`. Choose a fresh output directory for subsequent
builds. The build refuses a nonempty output directory, preventing stale reports
from accidentally being published. Only the generated output directory should be
uploaded to a static host. It contains HTML, CSS, JavaScript, and curated JSON;
no Python service, `.env`, database, debug output, or credentials are required.
Asset and data paths work under a subdirectory, including a GitHub Pages project
URL. Hash routes allow report links to be refreshed without server rewrites.

`showcase/manifest.json` defines the contact email and sample ordering. Public
report projections live in `showcase/reports/`. These files can be built offline,
without access to the private snapshots or API credentials.

## Generate and review samples privately

`showcase/candidates.json` records candidate addresses and the public property
pages used to identify them. It contains paths to local snapshots, not the
snapshots themselves. `scripts/generate_showcase_reports.py` reuses existing
snapshots and otherwise runs candidates serially with the normal pipeline caps.
It requires the local model plus `.env` credentials and incurs normal API usage.
An address must have exactly one Census match before a paid run begins.

Read both briefs and inspect the map, records, source excerpts, and coverage for
each candidate. Check geographic relevance, claims against citations, historical
versus current context, and useful source diversity. A finished brief is not a
quality score: sparse sources, owner marketing, dated discussions, uncertain
parcel matches, and capped maps must remain visible.

After local review, mark each candidate `recommended`, `qualified`, or `hold` in
`showcase/candidates.json`. Only recommended and qualified samples are included.
Then `scripts/curate_showcase.py` creates the public projections
and manifest. It holds reports missing either brief or mapped evidence. Review
`docs/showcase-review.md` for the current editorial assessment before publishing.

The projection removes raw county records (including owner/contact fields),
Census geography payloads, full retrieved web-page bodies, and internal case
setup fields. It retains source URLs, dates, attribution, map features, public
record summaries, exact cited excerpts, and the synthesized briefs. Legacy
Gemini-grounded responses are rejected by the public curator. The projection
is intentionally a display artifact, not a lossless downstream export.

## Deployment

Upload the contents of the generated directory to the static host you choose.
For GitHub Pages, use a Pages artifact built from this directory; for Cloudflare
Pages, select it as the build output directory. Do not run the private app on the
public host or configure model/search secrets there. Actual hosting setup and
publication are separate from building and previewing the artifact locally.

## GitHub Pages

The repository includes `.github/workflows/pages.yml`. Pushes to `main` and manual
workflow runs test the project offline, build the reviewed static samples, and
publish only `dist/showcase`. No model/search credentials are used or required.
Deployment permissions are restricted to the deploy job.

In the `surreal-estate` repository on GitHub, open Settings → Pages and select
GitHub Actions as the build source. Then open Actions → Deploy showcase → Run
workflow, selecting `main`. If a run triggered before Pages was enabled fails,
start a new manual run after changing the setting.

The project URL is `https://lucas-granucci.github.io/surreal-estate/`. Leave the
custom-domain setting empty to use that URL. The existing portfolio at
`https://lucas-granucci.github.io/` remains a separate site and repository.
