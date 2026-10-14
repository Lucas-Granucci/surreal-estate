---
target: webapp report readability
total_score: 25
max_score: 40
na_heuristics:
p0_count: 0
p1_count: 1
target_identity: "file:/Users/lucasgranucci/everything/projects/surreal-estate/surreal_estate/synthesis/dashboard.py"
target_fingerprint: "sha256:66ee321b0823b1e5b0347a04d381a0ce750d54510c6f06e396db27d6360c3ef1"
target_path: /Users/lucasgranucci/everything/projects/surreal-estate/surreal_estate/synthesis/dashboard.py
timestamp: 2026-10-12T17-56-36Z
slug: surreal-estate-synthesis-dashboard-py
---
# Webapp design review — 12 October 2026

Method: independent design-review agent; detector and browser checks completed by the parent after the evidence agent failed to return its results. This is a degraded dual-assessment run, not two successfully completed independent assessments.

User priority: finding and understanding report information. Scope: refine the incumbent report, preserving its colors, identity, content and evidence distinctions.

The app has a coherent, approachable visual identity. Its strongest qualities are explicit trust boundaries, source links, native disclosure controls, and deliberate address confirmation. The main opportunity is to put useful findings ahead of the mechanics of research.

## Baseline heuristic assessment

Source-based baseline; these scores are provisional and are not a post-change re-score.

| Heuristic | Score /4 | Baseline issue |
|---|---:|---|
| System status | 3 | Research state present; progress hierarchy limited |
| Real-world match | 3 | Internal vocabulary in reports |
| Control and freedom | 2 | Setup not persisted on refresh |
| Consistency | 3 | Navigation and section labels differ |
| Error prevention | 3 | Strong confirmation; default geography may confuse |
| Recognition over recall | 2 | Useful record text buried in disclosures |
| Efficiency | 2 | No report or saved-report search |
| Minimalist design | 2 | Collection metadata precedes findings |
| Error recovery | 3 | Reconnection lacks an alternate recovery action |
| Help | 2 | Evidence classes need clearer explanation |
| Total | 25/40 | Baseline: acceptable, with significant usability opportunities |

## Two priority areas

1. **P1 — Information hierarchy and comprehension.** Research statistics preceded useful findings, and statements were hidden behind source disclosures. Implemented a source-linked preview of up to three supported observations in existing report order, with qualifications, an explicit no-findings state, and links to all observations and gaps. Record statements are directly readable with provenance available on demand. Remaining work: clearer terminology and report-wide search. Relevant follow-up: impeccable clarify.
2. **P2 — Navigation and reading continuity on mobile.** The expanded navigation delayed the report content. Implemented a mobile navigation disclosure, automatic opening of destination sections, focus transfer, and responsive restoration of desktop navigation. In the 390px fixture, main content moved from y=864 to y=530. Removed repeated card entrance animations and the accidental error-panel styling on the coverage count. Relevant follow-up: impeccable adapt for larger real-world reports.

Power users benefit from more directly readable findings; keyboard users retain native disclosures and receive focus at navigation targets; mobile readers reach content sooner. Remaining cognitive load comes from verbose model responses and terminology. Saved-report search is a later opportunity, outside the user's selected priority for this pass.

## Detector and validation

The fallback CLI detector reported five findings: side-tab accent border (app.css:50), hero eyebrow, pulsing dot, marquee, and repeating gradient (index.html locations reported as line 0). The latter three need interpretation: the pulse class appears unused, the progress animation reflects actual research activity, and the stripe pattern is a timeline grid. The homepage eyebrow and legacy accent border were left outside the focused report changes.

43 dashboard/webapp tests pass, including a new regression covering finding order, escaping, qualifications, and source links. JavaScript syntax and diff whitespace checks pass. Headless Chromium inspected desktop/mobile fixtures in light and dark modes and verified navigation, focus, resizing, and expand/collapse. This does not substitute for assistive-technology testing or live provider research. No user-facing detector overlay was installed. The temporary local server was stopped; screenshots are retained under /private/tmp/surreal-design-review for reference.

Questions skipped: two priority areas; the user already selected finding and understanding report information.
