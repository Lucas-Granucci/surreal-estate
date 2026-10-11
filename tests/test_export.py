from argparse import Namespace

from test_frontend import outcome_fixture

from surreal_estate.cli import execute, main
from surreal_estate.evals.fixtures import fixture_case
from surreal_estate.models import ChannelResult, Coverage, Evidence, Observation, RunReport
from surreal_estate.policy.gate import PolicyGate
from surreal_estate.store.export import ResearchExport, build_export
from surreal_estate.synthesis.dossier import synthesize
from surreal_estate.synthesis.frontend import DevelopmentSnapshot


async def test_explicit_cli_export_contains_web_data_and_can_replace_file(tmp_path, monkeypatch):
    outcome = outcome_fixture()

    async def fixture_run(*args, **kwargs):
        return outcome

    monkeypatch.setattr("surreal_estate.cli.run", fixture_run)
    path = tmp_path / "exports" / "research.json"
    args = Namespace(command="demo", db=None, export=str(path))
    await execute(args)
    loaded = DevelopmentSnapshot.model_validate_json(path.read_text())
    assert loaded.web[0].response == outcome.displays[0].response
    assert loaded.web[1].response == outcome.displays[1].response
    assert '\n  "web": [\n' in path.read_text()
    assert "PRIVATE-DEBUG" not in path.read_text()
    await execute(args)
    assert DevelopmentSnapshot.model_validate_json(path.read_text()) == loaded


async def test_durable_export_remains_explicitly_filtered(tmp_path, monkeypatch):
    outcome = outcome_fixture()

    async def fixture_run(*args, **kwargs):
        return outcome

    monkeypatch.setattr("surreal_estate.cli.run", fixture_run)
    path = tmp_path / "durable.json"
    await execute(Namespace(command="demo", db=None, durable_export=str(path)))
    assert ResearchExport.model_validate_json(path.read_text()).report.id == outcome.report.id
    assert "PRIVATE" not in path.read_text()


def test_cli_saves_development_json_by_default_and_can_opt_out(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["surreal-estate", "demo"])
    main()
    snapshots = list((tmp_path / "exports").glob("*.json"))
    assert len(snapshots) == 1
    loaded = DevelopmentSnapshot.model_validate_json(snapshots[0].read_text())
    assert loaded.report.demo and loaded.report.claims
    assert "Development JSON: exports/" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["surreal-estate", "demo", "--no-save-json"])
    main()
    assert list((tmp_path / "exports").glob("*.json")) == snapshots


async def test_cli_exports_roundtrippable_fixture_with_provenance(tmp_path):
    path = tmp_path / "nested" / "research.json"
    outcome = await execute(Namespace(command="demo", db=None, export=str(path)))
    bundle = DevelopmentSnapshot.model_validate_json(path.read_text())
    assert bundle.report.id == outcome.report.id
    assert bundle.schema_version == "1.0"
    assert bundle.report.demo
    assert bundle.report.claims
    assert bundle.report.claims[0].evidence_ids[0] == bundle.report.result.evidence[0].id
    assert not bundle.report.trace


def test_export_excludes_grounded_text_and_rebuilds_claims():
    evidence = Evidence(
        provider="gemini_search",
        uri="https://example.org/private",
        title="SECRET",
        excerpt="SECRET",
        retention="persistent",
        kind="reported",
    )
    observation = Observation(
        topic="restaurant_reviews",
        statement="SECRET",
        evidence_ids=[evidence.id],
        location_scope="Pittsburgh",
        observed_on=fixture_case().as_of,
        qualifier="reported",
        confidence=0.8,
    )
    result = ChannelResult(
        evidence=[evidence],
        observations=[observation],
        coverage=[
            Coverage(channel="web", topic="restaurant_reviews", status="complete", reason="SECRET")
        ],
    )
    report = RunReport(
        case=fixture_case(), result=result, claims=synthesize(result), trace=["SECRET"]
    )
    bundle = build_export(report, PolicyGate())
    assert "SECRET" not in bundle.model_dump_json()
    assert not bundle.report.claims
    assert bundle.omissions.web_topics == ["restaurant_reviews"]
    assert bundle.omissions.evidence_count == bundle.omissions.observation_count == 1
