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
    coverage = [c for c in report.result.coverage
                if c.channel not in {"web", "fact_checker"} or c.provider == "tavily_search"]
    research = []
    for w in report.result.research:
        brief = w.brief
        if brief:
            paragraphs = [brief.overview] + [p for s in brief.sections for p in s.paragraphs]
            if any(c.evidence_id not in allowed for p in paragraphs for c in p.citations):
                brief = None
        research.append(w.model_copy(update={
            "evidence_ids": [i for i in w.evidence_ids if i in allowed],
            "findings": [f for f in w.findings if all(c.evidence_id in allowed for c in f.citations)],
            "brief": brief, "summary": w.summary if brief else "",
            "synthesis_status": w.synthesis_status if brief or w.brief is None else "not_run",
        }))
    result = ChannelResult(evidence=evidence, observations=observations, coverage=coverage,
                           research=research)
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
