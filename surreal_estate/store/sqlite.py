import json

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, insert, select

from surreal_estate.models import ChannelResult, RunReport
from surreal_estate.policy.gate import PolicyGate
from surreal_estate.synthesis.dossier import synthesize


def durable_report(report: RunReport, policy: PolicyGate) -> RunReport:
    """Shared persistence/export boundary; never retain transient derived claims."""
    evidence = [e for e in report.result.evidence if policy.persistable(e)]
    allowed = {e.id for e in evidence}
    observations = [o for o in report.result.observations if set(o.evidence_ids) <= allowed]
    coverage = [c for c in report.result.coverage if c.channel not in {"web", "fact_checker"}]
    result = ChannelResult(evidence=evidence, observations=observations, coverage=coverage)
    return report.model_copy(update={"result": result, "claims": synthesize(result), "trace": []})


class Store:
    def __init__(self, path: str):
        self.engine = create_engine("sqlite+pysqlite:///" + path)
        metadata = MetaData()
        self.runs = Table(
            "runs",
            metadata,
            Column("id", String, primary_key=True),
            Column("payload", Text, nullable=False),
        )
        metadata.create_all(self.engine)

    def save(self, report: RunReport, policy: PolicyGate):
        durable = durable_report(report, policy)
        with self.engine.begin() as connection:
            connection.execute(
                insert(self.runs).values(id=report.id, payload=durable.model_dump_json())
            )

    def load(self, run_id: str) -> RunReport:
        with self.engine.connect() as connection:
            payload = connection.execute(
                select(self.runs.c.payload).where(self.runs.c.id == run_id)
            ).scalar_one()
        return RunReport.model_validate(json.loads(payload))

    def close(self):
        self.engine.dispose()
