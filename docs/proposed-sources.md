# Proposed sources for Pittsburgh property research

This catalog distinguishes enabled integrations from later roadmap candidates. Initial geography:
Pittsburgh and Allegheny County, Pennsylvania. Source documentation reviewed
2026-10-11. WPRDC adapters resolve current resource IDs from catalog metadata
each run; catalog changes fail closed rather than selecting an archived resource.

## Current implementation

Channel A includes the **U.S. Census Geocoder**, **Allegheny County assessments**,
**Pittsburgh PLI permits**, **FEMA NFHL**, **OpenStreetMap / Overpass**, and
**Pittsburgh DOMI street closures** by default in live research. All are key-free.
Census geographic identifiers gate county/city sources. Assessments require a
unique exact address match; permits require that parcel. Closure lookup is bounded
to same-street segments within 1 km, not every nearby street. OSM uses the
[main Overpass instance](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances),
with provider failures recorded independently. See the README for limits.

Live verification on 2026-10-11 returned Census, assessment, PLI, FEMA and closure
records. The initial Private.coffee Overpass endpoint returned HTTP 500. Switching
to the main endpoint with raw Overpass QL, an identifying project User-Agent, and
a 35-second request window restored results. The adapter now emits four concise
area summaries (schools, groceries, transit stops, pharmacies), with at most 50
supporting map objects per category held in expandable details. Restaurants,
cafés, parks and clinics are excluded from the default query.

Channel B has an explicit
not-implemented placeholder; there is no file-upload flow yet. Channel C already
uses **Gemini API with Google Search grounding**, with separate neighborhood
discussion and nearby restaurant review prompts. A separate local Nemotron role
plans fact checks, which Gemini performs as a grounded refinement of its answer.

The viewer's **Sources for this run** section inventories returned evidence and
recorded attempts, not this proposed catalog. Open-web URLs come from each actual
response's grounding chunks, with cited/uncited distinctions and deduplication
across search and re-check. Google redirect URLs are preserved; their destination
domains are not guessed or fetched. Development JSON includes those original
chunks and support mappings.

## Channel A: API and structured-data candidates

| Source | Proposed use | Access and implementation notes | Priority |
| --- | --- | --- | --- |
| [U.S. Census Geocoder](https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html) | Address normalization, coordinates; later census geographic identifiers | REST API; already implemented for address matching. Coordinates are address-range interpolation, not proof of parcel boundaries. Geography lookup is now included; tract/block-group analyses remain later work. | Current |
| [Allegheny County property assessments via WPRDC](https://data.wprdc.org/dataset/property-assessments) | Parcel ID, recorded building characteristics, assessment values, recorded sale attributes; compare against listing documents | Dataset offers an API-oriented resource through CKAN. Resolve the current resource and inspect its data dictionary. Display publication date and match confidence. Assessments are dynamic records, not appraisals or proof of structural condition. | Enabled |
| [Pittsburgh PLI permits via WPRDC](https://data.wprdc.org/dataset/pli-permits) | Issued building, mechanical, electrical and other permit records near/on the parcel | Structured dataset, published from the city's permitting system. Includes records from June 2019 onward. Include the newer Building & Development Application type as well as older building permits. Plumbing permits are outside this dataset. Check the resource's API availability before choosing CKAN DataStore vs a bounded data-file adapter. | Enabled |
| [FEMA National Flood Hazard Layer](https://www.fema.gov/flood-maps/national-flood-hazard-layer) | Mapped flood zone, map effective date and coverage limitations | GIS services/digital map products. Query the mapped location and retain layer/map identifiers. A point result with interpolated coordinates is preliminary context; it is not a guarantee that a parcel or building will not flood. | Enabled |
| [OpenStreetMap / Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) | Area summaries for schools, grocery stores, public transit stops and pharmacies | Query bounded areas, preserve OSM object IDs/tags and attribution, and respect endpoint limits. Missing data does not imply absence. Geometric proximity and travel time are different quantities; routing is a later adapter. [OSM license and attribution](https://www.openstreetmap.org/copyright). | Enabled |
| [Pittsburgh DOMI street closures via WPRDC](https://data.wprdc.org/dataset/street-closures) | Planned/recorded street closure context near the address | Use this current feed rather than the archived right-of-way permit dataset. Preserve closure dates and status; a permit is not proof that work is currently underway. Verify update completeness and spatial fields. | Enabled |
| [Census ACS five-year API](https://www.census.gov/data/developers/data-sets/acs-5year.html) | Aggregate housing characteristics and commute context, if requested | Resolve the available release, geography and variables; keep margins of error and vintage. These are area estimates, not facts about the property or its occupants. Avoid demographic desirability, steering and school-quality rankings. | Later |
| [EPA Envirofacts Data Service API](https://www.epa.gov/enviro/envirofacts-data-service-api) | Nearby facility/program records and environmental questions to investigate | EPA provides a data-service API over multiple databases. Pick a concrete program/table before implementation, record its update date, and explain geographic matching. Facility proximity alone is not proof of exposure or contamination. | Later |
| [National Weather Service API](https://www.weather.gov/documentation/services-web-api) | Optional current alerts/forecast context for a visit | Documented API; follow its identification and caching requirements. Weather alerts are time-sensitive and should remain separate from enduring property claims. | Optional |

City of Pittsburgh permits and closures do not cover every Allegheny County
municipality. Resolve municipal jurisdiction before lookup. Keep parcel/address
matches explicit and report ambiguous matches rather than attaching a neighbor's
record. An empty search means no records returned by that query, not proof of
absence of work, hazards or amenities.

Pittsburgh Regional Transit stops/routes and published GTFS feeds are another
candidate after the initial adapters. Verify the current publisher endpoint,
feed license, service calendar and refresh cadence before committing to an API;
scheduled service alone does not establish real-time arrival or commute time.

## Channel B: user-provided evidence candidates

| Input | Proposed output | Provenance and limits |
| --- | --- | --- |
| Listing PDF or screenshots | Stated room counts, dimensions, amenities and listing assertions | Document/file identifier, page number and supporting text/region; preserve listing assertions as reported until checked against records. |
| Floorplans | Stated dimensions, layout and questions about circulation | Page/region citations; do not silently treat an unscaled drawing as an exact measurement. |
| User-supplied photos | Visible-feature descriptions and follow-up questions | File/region citations; photos should generate inspection questions rather than structural or legal conclusions. |
| HOA/condominium documents, budgets, minutes and CC&Rs | Documented fees, restrictions, dated decisions and questions | Prefer supplied governing documents over search snippets. Keep version, page and effective date; no legal verdicts. |
| Inspection reports and seller disclosures | Attributed disclosed findings and unresolved questions | Keep document/page references and report date. Separate the author's statement from independent confirmation. |

These are proposals only. Add an input manifest when uploads are implemented so
the top-of-viewer inventory can list supplied filenames, document types and
processing status, including files that fail extraction. Do not count generated
questions as factual evidence.

## Channel C: open-web discovery candidates

Continue using Gemini's [Google Search grounding tool](https://ai.google.dev/gemini-api/docs/google-search/).
It supplies answer text, source chunks, support mappings and Search Suggestions.
Gemini is the retrieval/synthesis provider; the linked publishers are the sources.
Keep these identities separate in the viewer and JSON. This proposal does not
switch restaurant discovery to Google Places or introduce a crawler.

| Source family | Candidate sites/pages | Intended use |
| --- | --- | --- |
| Official local government | City/county planning pages, public meeting agendas/minutes, municipal notices and project pages | Discover dated development and governance context. Confirm material property-specific structural/legal statements using Channel A records or Channel B documents. Municipal coverage matters. |
| Transportation projects | [PennDOT Projects Near You](https://gis.penndot.pa.gov/paprojects), district notices, Pittsburgh DOMI project pages, transit announcements | Distinguish proposals, funded projects and active construction; retain geography, announcement date and scheduled dates. |
| Local journalism | [WESA](https://www.wesanews.org/), [PublicSource](https://www.publicsource.org/), local newspaper coverage when accessible | Context on neighborhood changes, development and transportation. Attribute reporting and keep publication dates; inaccessible/paywalled coverage should remain a coverage limitation. |
| Food publications | [Pittsburgh City Paper Food + Drink](https://www.pghcitypaper.com/category/food-drink/), [Pittsburgh Magazine](https://www.pittsburghmagazine.com/), accessible local food reporting | Nearby restaurant identity and recent review/reputation themes. Editorial reviews, promotional articles and customer opinions are different evidence types. |
| Customer reviews | Search-visible Yelp, Google Reviews and other restaurant review pages | Retain brief, attributed positive/negative themes labeled opinion. Broad semantic queries remain the default; no Yelp exclusivity or requirement to prove an exact radius. Do not invent ratings or counts. |
| Community discussions | Search-visible r/pittsburgh discussions, neighborhood forums and association announcements | Useful attributed perspectives and questions to check; avoid poster identities and statements such as “residents say.” A discussion is not representative polling. |
| Public HOA/condominium pages | Association websites, published notices/minutes, publicly accessible documents | Discover organization names and dated public context. Prefer user-provided governing documents for property-specific obligations. Missing accessible sources is an honest empty result. |
| Business/venue websites | Restaurant menus, official hours/contact pages, park and cultural venue sites | Corroborate identity and basic venue details; promotional descriptions do not independently validate customer opinions. |

Source families guide prompts; they are not guarantees that a given site will be
returned by Google. Keep multiple complementary searches, broad restaurant
discovery, address anchor/radius metadata, and recency context. Do not infer exact
distance from search snippets. Preserve useful opinions with attribution; check
factual components separately. Repeated citations to the same publisher are not
independent corroboration.

Gemini display responses keep original text, associated links and Search Suggestions.
Local development snapshots support reviewing the display; the filtered SQLite
and durable-processing path remains separate. Revisit provider terms and output
rights when adding production persistence or another analysis model. See the
[Gemini API terms](https://ai.google.dev/gemini-api/terms) and
[frontend response contract](frontend-response.md). Do not fetch cited pages merely
because a grounding chunk linked to them; any direct-fetch adapter needs its own
source policy.

## Proposed implementation order

1. Implemented: assessments, PLI, FEMA, OSM and same-street DOMI closures, with
   bounded requests, source policies, metadata, attribution and matching fixtures.
2. Next structured work: improve unit/parcel selection, expand closure spatial coverage,
   add caching and verify provider availability before expanding to ACS/EPA.
3. Implement the upload manifest and page-cited document extraction for Channel B.
4. Expand Gemini specialists to government/projects and HOA context only after
   evals show correct geography, support and useful coverage on those topics.

Each new API returns the shared `ChannelResult` and names its provider in coverage,
including unsuccessful attempts. Evidence needs source/record identifiers,
retrieval date, record date where available and matching limitations. Proposed
sources must never appear as “used” in a run until that run actually returned
evidence or recorded an attempt. Track citation support, wrong-property/geography
matches, opinion retention, empty coverage and per-property call cost.
