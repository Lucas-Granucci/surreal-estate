"""Build a static, read-only showcase from explicitly curated public projections."""
import json
import re
import shutil
from pathlib import Path

from surreal_estate.synthesis.frontend import build_frontend_response, load_snapshot_outcome
from surreal_estate.webapp.display import bench_response

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DETAIL_FIELDS = {
    'census': {'latitude', 'longitude', 'matched_address', 'benchmark', 'vintage'},
    'openstreetmap': {'category', 'query_radius_m', 'mapped_feature_count', 'count_is_lower_bound',
                     'nearest_returned_center_distance_m', 'members', 'cached_response_retrieved_at',
                     'cache_stale', 'license_url'},
    'wprdc_closures': {'approximate_segment_distance_m', 'radius_m'},
    'tavily_search': {'content_kind', 'topic'},
}
RECORD_FIELDS = {'primary_street', 'from_street', 'to_street', 'work_description', 'from_date', 'to_date'}


def public_report(snapshot: str) -> dict:
    """Publish display evidence, never raw county records, full pages, or model traces."""
    outcome = load_snapshot_outcome(snapshot)
    if outcome.displays:
        raise ValueError('Legacy grounded responses cannot be included in the public showcase')
    bench = bench_response(build_frontend_response(outcome))
    for evidence in bench['evidence']:
        if evidence['kind'] == 'user_document' or evidence['retention'] != 'persistent':
            raise ValueError('Private or ephemeral evidence cannot be published')
        details = evidence['details']
        evidence['details'] = {k: v for k, v in details.items()
                               if k in DETAIL_FIELDS.get(evidence['provider'], set())}
        if evidence['provider'] == 'openstreetmap':
            evidence['details']['members'] = [
                {k: v for k, v in member.items() if k in {
                    'object_type', 'object_id', 'uri', 'name', 'center',
                    'approximate_center_distance_m'}}
                for member in details.get('members', [])]
        if evidence['provider'] == 'wprdc_closures':
            evidence['details']['record'] = {k: v for k, v in details.get('record', {}).items()
                                             if k in RECORD_FIELDS}
    # Case priorities and parcel choices are internal setup, not public display context.
    bench['case'] = {k: bench['case'][k] for k in ['address', 'geography', 'as_of']}
    return bench


def build_showcase(source: str = 'showcase', output: str = 'dist/showcase') -> Path:
    source_dir, target = Path(source), Path(output)
    if target.resolve() == source_dir.resolve() or source_dir.resolve() in target.resolve().parents:
        raise ValueError('Build output must be separate from curated input')
    manifest = json.loads((source_dir / 'manifest.json').read_text())
    if not manifest.get('reports'):
        raise ValueError('Select at least one sample report')
    contact = manifest.get('contact_email', '')
    if not re.fullmatch(r'[^\s<>"@]+@[^\s<>"@]+\.[^\s<>"@]+', contact):
        raise ValueError('A valid contact email is required')
    reports = []
    for entry in manifest['reports']:
        identifier = entry['id']
        if not SLUG.fullmatch(identifier):
            raise ValueError('Invalid sample identifier')
        report = json.loads((source_dir / 'reports' / f'{identifier}.json').read_text())
        if report.get('web'):
            raise ValueError('Only Tavily-backed public projections may be built')
        reports.append((identifier, report))
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError('Build output must be empty; choose a fresh directory')
    static = Path(__file__).parent / 'static'
    for name in ['app.js', 'app.css', 'favicon.svg']:
        shutil.copyfile(static / name, target / name)
    html = (static / 'index.html').read_text().replace('href="/app.css"', 'href="./app.css"')
    html = html.replace('href="/favicon.svg"', 'href="./favicon.svg"')
    html = html.replace('<html lang="en">', '<html lang="en" data-showcase="true">')
    html = html.replace('<script src="/app.js" defer></script>',
                        '<script src="./showcase-config.js"></script>\n    <script src="./app.js" defer></script>')
    html = html.replace('Enable JavaScript to research an address and open saved\n      reports.',
                        'Enable JavaScript to explore the sample reports.')
    html = html.replace('<title>', '<meta name="description" content="Explore real Pittsburgh address research: mapped places, public records, and source-linked local intelligence." />\n    <title>', 1)
    (target / 'index.html').write_text(html)
    (target / 'showcase-config.js').write_text('window.SURREAL_SHOWCASE = ' +
        json.dumps({'contactEmail': contact}) + ';\n')
    directory = target / 'data' / 'reports'
    directory.mkdir(parents=True)
    (target / 'data' / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for identifier, report in reports:
        (directory / f'{identifier}.json').write_text(json.dumps(report, ensure_ascii=False) + '\n')
    (target / '.nojekyll').touch()
    return target
