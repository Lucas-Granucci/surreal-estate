import json

import pytest
from test_frontend import outcome_fixture

from surreal_estate.models import Evidence
from surreal_estate.synthesis.frontend import save_development_snapshot
from surreal_estate.webapp.showcase import build_showcase, public_report


def test_public_projection_excludes_raw_records_and_internal_fields(tmp_path):
    outcome = outcome_fixture()
    outcome.displays = []
    evidence = Evidence(provider="census", uri="https://geocoding.geo.census.gov/", title="Address",
                        excerpt="Matched address", retention="persistent", kind="official_record")
    outcome.report.result.evidence.append(evidence)
    evidence.details.update(record={'OWNER': 'PRIVATE OWNER', 'phone': 'PRIVATE PHONE'},
                            debug={'api_key': 'PRIVATE KEY'}, content='FULL PAGE')
    snapshot = save_development_snapshot(outcome, path=str(tmp_path / 'snapshot.json'))
    report = public_report(str(snapshot))
    serialized = json.dumps(report)
    for excluded in ['PRIVATE OWNER', 'PRIVATE PHONE', 'PRIVATE KEY', 'FULL PAGE']:
        assert excluded not in serialized
    assert report['evidence'][0]['uri'] == str(evidence.uri)
    assert report['evidence'][0]['excerpt'] == evidence.excerpt
    assert set(report['case']) == {'address', 'geography', 'as_of'}


def test_showcase_rejects_saved_grounding(tmp_path):
    snapshot = save_development_snapshot(outcome_fixture(), path=str(tmp_path / 'snapshot.json'))
    with pytest.raises(ValueError, match='Legacy grounded'):
        public_report(str(snapshot))


def make_input(tmp_path, identifier='sample'):
    source = tmp_path / 'curated'
    (source / 'reports').mkdir(parents=True)
    manifest = {'contact_email': 'person@example.com', 'reports': [{'id': identifier}]}
    (source / 'manifest.json').write_text(json.dumps(manifest))
    (source / 'reports' / 'sample.json').write_text(json.dumps({'web': [], 'case': {'address': 'Example'}}))
    return source


def test_static_build_is_subpath_safe_and_contains_no_backend(tmp_path):
    source = make_input(tmp_path)
    target = build_showcase(str(source), str(tmp_path / 'site'))
    html = (target / 'index.html').read_text()
    assert 'src="./app.js"' in html and 'href="./app.css"' in html
    assert 'showcase-config.js' in html
    assert 'data-showcase="true"' in html
    assert (target / 'data/reports/sample.json').exists()
    assert not list(target.rglob('*.py'))
    assert not list(target.rglob('.env'))
    with pytest.raises(ValueError, match='empty'):
        build_showcase(str(source), str(target))


def test_build_rejects_path_traversal_before_copying(tmp_path):
    source = make_input(tmp_path, '../private')
    with pytest.raises(ValueError, match='identifier'):
        build_showcase(str(source), str(tmp_path / 'site'))
    assert not (tmp_path / 'site').exists()


def test_public_projection_rejects_private_documents(tmp_path):
    outcome = outcome_fixture()
    outcome.displays = []
    outcome.report.result.evidence.append(Evidence(
        provider="user", uri="https://example.org/private", title="Private", excerpt="Private",
        retention="persistent", kind="user_document"))
    snapshot = save_development_snapshot(outcome, path=str(tmp_path / 'snapshot.json'))
    with pytest.raises(ValueError, match='Private or ephemeral'):
        public_report(str(snapshot))


def test_curated_samples_have_maps_briefs_and_resolved_citations():
    from pathlib import Path

    source = Path(__file__).parents[1] / 'showcase'
    manifest = json.loads((source / 'manifest.json').read_text())
    assert len(manifest['reports']) >= 5
    for entry in manifest['reports']:
        report = json.loads((source / 'reports' / f"{entry['id']}.json").read_text())
        evidence = {e['id']: e for e in report['evidence']}
        assert any(e['provider'] == 'openstreetmap' for e in evidence.values())
        assert len(report['research']) == 2
        for research in report['research']:
            assert research['brief'] and research['synthesis_status'] == 'complete'
            paragraphs = [research['brief']['overview']] + [
                p for section in research['brief']['sections'] for p in section['paragraphs']]
            for paragraph in paragraphs:
                assert paragraph['citations']
                assert all(c['evidence_id'] in evidence and c['excerpt'] for c in paragraph['citations'])
        for item in evidence.values():
            assert 'content' not in item['details']
            assert not set(item['details'].get('record', {})) - {
                'primary_street', 'from_street', 'to_street', 'work_description', 'from_date', 'to_date'}
