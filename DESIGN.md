---
"name": "SurrealEstate"
"description": "Evidence Bench: graphite surfaces, IBM Plex Sans and source-aware local knowledge."
"colors":
  "bg": "#f6f6f7"
  "surface": "#ffffff"
  "raised": "#fafafb"
  "text": "#1d1d20"
  "muted": "#60606b"
  "border": "#dadae0"
  "control": "#858591"
  "accent": "#303038"
  "onaccent": "#ffffff"
  "link": "#365b9d"
  "focus": "#3269d7"
  "selected": "#ececf0"
  "hover": "#f1f1f4"
  "disabled": "#73737f"
  "disabledBg": "#e9e9ed"
  "warning": "#8a4b08"
  "warningBg": "#fff5e5"
  "error": "#b42e3e"
  "errorBg": "#fff0f2"
  "success": "#216444"
  "successBg": "#edf7f0"
  "unknown": "#60606b"
  "unknownBg": "#ececf0"
  "dark-bg": "#111113"
  "dark-surface": "#19191d"
  "dark-raised": "#222227"
  "dark-text": "#f3f3f5"
  "dark-muted": "#b1b1bb"
  "dark-border": "#35353d"
  "dark-control": "#777782"
  "dark-accent": "#ebebf0"
  "dark-onaccent": "#17171b"
  "dark-link": "#9bbeff"
  "dark-focus": "#aec9ff"
  "dark-selected": "#2c2c35"
  "dark-hover": "#24242b"
  "dark-disabled": "#a3a3ae"
  "dark-disabledBg": "#29292f"
  "dark-warning": "#f0bd72"
  "dark-warningBg": "#302417"
  "dark-error": "#ffafb7"
  "dark-errorBg": "#351d24"
  "dark-success": "#8dd5ae"
  "dark-successBg": "#182d24"
  "dark-unknown": "#b1b1bb"
  "dark-unknownBg": "#28282f"
"typography":
  "display":
    "fontFamily": "\"IBM Plex Sans\", Arial, sans-serif"
    "fontSize": "clamp(44px, 5.6vw, 72px)"
    "fontWeight": 500
    "lineHeight": 1.02
    "letterSpacing": "-0.055em"
  "headline":
    "fontFamily": "\"IBM Plex Sans\", Arial, sans-serif"
    "fontSize": "36px"
    "fontWeight": 500
    "lineHeight": 1.15
    "letterSpacing": "-0.035em"
  "section":
    "fontFamily": "\"IBM Plex Sans\", Arial, sans-serif"
    "fontSize": "25px"
    "fontWeight": 500
    "lineHeight": 1.15
    "letterSpacing": "-0.035em"
  "finding":
    "fontFamily": "\"IBM Plex Sans\", Arial, sans-serif"
    "fontSize": "18px"
    "fontWeight": 500
    "lineHeight": 1.15
    "letterSpacing": "-0.02em"
  "body":
    "fontFamily": "\"IBM Plex Sans\", Arial, sans-serif"
    "fontSize": "16px"
    "fontWeight": 400
    "lineHeight": 1.5
  "control":
    "fontFamily": "\"IBM Plex Sans\", Arial, sans-serif"
    "fontSize": "14px"
    "fontWeight": 500
    "lineHeight": 1.4
  "qualifier":
    "fontFamily": "\"IBM Plex Sans\", Arial, sans-serif"
    "fontSize": "13px"
    "fontWeight": 400
    "lineHeight": 1.5
  "raw":
    "fontFamily": "ui-monospace, SFMono-Regular, Consolas, monospace"
    "fontSize": "12px"
    "lineHeight": 1.55
"rounded":
  "raw": "4px"
  "previewNavigation": "5px"
  "control": "6px"
  "choice": "7px"
  "panel": "10px"
"spacing":
  "8": "8px"
  "10": "10px"
  "12": "12px"
  "14": "14px"
  "16": "16px"
  "18": "18px"
  "20": "20px"
  "22": "22px"
  "24": "24px"
  "25": "25px"
  "27": "27px"
  "30": "30px"
  "32": "32px"
  "40": "40px"
  "48": "48px"
  "52": "52px"
"components":
  "button-primary":
    "backgroundColor": "{colors.accent}"
    "textColor": "{colors.onaccent}"
    "typography": "{typography.control}"
    "rounded": "{rounded.control}"
    "padding": "10px 16px"
  "button-primary-hover":
    "backgroundColor": "{colors.text}"
  "button-secondary":
    "backgroundColor": "{colors.surface}"
    "textColor": "{colors.text}"
    "typography": "{typography.control}"
    "rounded": "{rounded.control}"
    "padding": "10px 16px"
  "button-text":
    "backgroundColor": "transparent"
    "textColor": "{colors.text}"
    "rounded": "{rounded.control}"
    "padding": "10px 16px"
  "field":
    "backgroundColor": "{colors.surface}"
    "textColor": "{colors.text}"
    "rounded": "{rounded.control}"
    "padding": "14px 16px"
  "channel":
    "backgroundColor": "transparent"
    "rounded": "{rounded.choice}"
    "padding": "23px 18px"
  "channel-selected":
    "backgroundColor": "{colors.selected}"
  "preview-card":
    "backgroundColor": "{colors.surface}"
    "rounded": "{rounded.panel}"
  "nav-active":
    "backgroundColor": "{colors.selected}"
    "textColor": "{colors.text}"
    "padding": "10px 16px"
  "finding-selected":
    "backgroundColor": "{colors.selected}"
    "padding": "23px 12px"
---

# Design System: SurrealEstate

## Overview

**Creative North Star: "Evidence Bench"**

The Evidence Bench puts concise findings beside inspectable evidence. Graphite controls, quiet neutral surfaces and IBM Plex Sans create a restrained working interface with a confident editorial landing page. The system follows the operating system’s light or dark preference without a theme toggle.

The user-approved `design/SurrealEstate.html` establishes the visual world. The shipped stylesheet and application retain its composition and components while binding them to real saved reports, research progress and source records. PRODUCT.md remains the authority for product truth.

**Key Characteristics:**

- Graphite actions and layered neutral surfaces in two system-controlled themes.
- IBM Plex Sans throughout, with large landing typography and compact evidence reading.
- An Evidence Bench with navigation, findings and a source inspector.
- Conventional choices and progressive disclosure that keep qualifications visible.

## Colors

Graphite and near-neutral grays carry the interface; restrained semantic colors identify links, focus and status. Frontmatter records the exact shipped light tokens and their `dark-` equivalents. The media query swaps the same CSS roles, including native control color-scheme.

### Primary

**Graphite action** (`accent`, `onaccent`) supplies primary buttons, selected-row edges and native checkbox/radio accents. Hover uses `text`. This role reverses to pale graphite on dark surfaces.

### Secondary

**Link blue** (`link`) marks source links; **focus blue** (`focus`) marks keyboard interaction. Warning, error, success and unknown foreground/background pairs describe state. They are not alternate brand colors.

### Neutral

**Canvas** (`bg`), **surface** (`surface`) and **raised evidence** (`raised`) form the bench. Primary text (`text`) and secondary text (`muted`) supply hierarchy. Quiet dividers (`border`) differ from stronger control strokes (`control`). `selected` and `hover` convey interaction; `disabled` and `disabledBg` make unavailable controls explicit.

**The System Theme Rule.** Follow the system preference using the paired light and dark tokens; provide no manual theme switch.

**The Evidence Meaning Rule.** Use readable source and status labels; color never upgrades uncertain evidence into a fact.

## Typography

IBM Plex Sans is embedded in the shipped CSS at weights 400, 500, 600 and 700, with Arial and sans-serif fallbacks. Headings normally use weight 500. The landing display tightens tracking and line height; working screens use compact, readable headings. Raw source records alone use the monospace role.

The frontmatter captures the reused roles. The report address is 34px, inspector heading 23px, setup heading 36px and finding heading 18px. Body copy is 16px; finding descriptions are 15px; qualifiers and metadata are 12–14px. Paragraphs default to a 68ch maximum, report introductions to 55ch and channel explanations to 42ch. At 720px and below, the landing heading is 46px, setup heading 31px, report address 30px and finding heading 17px.

## Layout

The landing composition is a left-aligned editorial hero, a wide three-column report preview, two separated value rows and a coverage disclosure. The hero is capped at 1120px with 32px side padding; the preview wrapper at 1192px with 32px side padding; value rows at 1056px. The header is 72px tall. Setup uses a centered 568px container with 24px side padding; saved reports use a 1000px container with 32px side padding.

The full-width report grid uses a 176px navigation rail, flexible findings column and 340px evidence inspector. Findings have 32px horizontal padding; the inspector has 25px. At 1500px and above, columns become 200px / flexible / 390px and the findings padding grows to 52px. Above 1120px, the inspector is sticky, independently scrollable and capped to the viewport.

At 1120px and below, the report uses a 160px rail and flexible content, and evidence opens in a dialog. The preview remains three columns at 140px / flexible / 265px. At 720px and below, the header becomes 64px, the report rail becomes a horizontally scrollable top navigation, findings use 20px side padding and evidence becomes a full-screen dialog. The preview stacks and hides its rail. Value rows stack, saved rows stack, and filter buttons use two columns instead of five. These are the shipped breakpoints; there is no 900px or 600px layout rule.

Findings reserve an 82px action column. Controls must remain legible without clipped text. Long source names and raw content wrap; tables and raw records may scroll locally.

## Elevation & Depth

Tonal surfaces and one-pixel borders provide everyday structure. The landing preview has a faint ambient shadow; the evidence dialog has a stronger floating shadow and a dimmed, blurred backdrop. Selected findings use an inset graphite edge. The world is restrained, not universally shadow-free.

**The Bench Depth Rule.** Keep the report’s structure in borders and tonal surfaces; reserve floating elevation for the preview and dialog patterns already present.

The preview shadow is `0 14px 40px #00000006`; the dialog shadow is `0 25px 90px #0003`; the backdrop is `#0007` with 3px blur. Focus is a 3px outline with 3px offset. Buttons transition background and border over 150ms and move down 1px when pressed. Screen entry is 180ms ease-out with a 3px rise. The active-stage spinner rotates over one second. Reduced motion removes animation and transitions, disables smooth scrolling and gives the spinner a dotted border.

## Shapes

Controls use 6px corners, candidate/channel choices 7px, the preview and desktop dialog 10px, and raw-record containers 4px. The selected preview navigation uses 5px corners. Borders and horizontal separators organize records; report rows are not floating cards. The mobile evidence dialog is square-cornered and fills the viewport.

## Components

### Buttons and fields

Primary buttons use graphite with its paired foreground, secondary buttons use the surface and a quiet border, and text buttons are transparent with a selected tint on hover. Buttons normally have a 44px minimum height. Source links use underlined link blue. Disabled controls use the explicit disabled pair and unavailable cursor. Text/search fields are at least 52px high with stronger control borders; invalid fields use the error border. Interactive controls retain the global focus treatment.

### Choices

Address matches wrap native radios in bordered candidates. Checked candidates use an accent border and selected fill. Research channels use native checkboxes with title and brief explanation; selected rows gain a quiet border and selected fill. Unavailable web options remain visibly disabled, with readiness status and a recheck action. Do not redesign them as exotic controls.

### Navigation and filters

The report navigation marks the current view with selected fill, medium weight and a two-pixel graphite edge. Views are Findings, Unresolved, Sources and Research scope. Filter buttons mark selection through `aria-pressed` and a selected fill. Five equal columns become two on mobile. There is no separate source-tag component in the shipped interface; source distinctions appear as text qualifiers and inspector metadata.

### Findings and evidence

Findings lead with title, concise statements and visible qualifiers. Inspecting a row selects it and opens the corresponding source context in the desktop inspector or smaller-screen dialog. Source links, limitations, selected records and raw data remain accessible. Records use separators. Unknown, blocked, unavailable and failed coverage remain distinct; model summaries and AI reviews remain separate from public records and community mapping.

### Progress, recovery and saved reports

Progress shows actual backend Waiting, In progress, Finished, Stopped and Not run states, with a status message. Loading, unavailable research, no address match, interruption, reconnect and empty saved-report states use the same compact hierarchy. Completion offers the report action. Saved reports are searchable rows, not a decorative card grid. Never turn milestone states into fabricated completion percentages.

### Landing preview and disclosure

The landing preview uses returned saved-report findings and available distance data, or an honest empty state. It does not seed fictional property facts. Nearby distances describe returned mapped features, not travel routes. Native disclosures expose location qualifications, additional records, raw data and coverage. The preview’s composition belongs to this surface; it is not a requirement for every future screen.

## Do's and Don'ts

### Do:

- Do preserve the approved graphite palette and system-controlled themes.
- Do keep source classes, missing data and address estimates explicit.
- Do pair concise findings with reachable evidence and complete source records.
- Do preserve keyboard focus, native controls and reduced-motion behavior.

### Don't:

- Don’t add a theme toggle or revive the superseded green action palette.
- Don’t substitute system display typography for IBM Plex Sans.
- Don’t invent report content, travel times or generation percentages.
- Don’t present model accounts as independently verified findings or permits as active work.
