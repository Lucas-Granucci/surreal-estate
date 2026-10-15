"""Versioned downstream handoff using the same retention boundary as SQLite."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from surreal_estate.models import Model, RunReport
from surreal_estate.policy.gate import PolicyGate
from surreal_estate.store.sqlite import durable_report


class ExportOmissions(Model):
    grounded_content: Literal["excluded"] = "excluded"
    debug_payloads: Literal["excluded"] = "excluded"
    web_topics: list[str]
    evidence_count: int
    observation_count: int
    reason: str = (
        "Live Gemini search answers and re-checks are display-only under the current policy; "
        "they are not inputs for downstream processing. Debug payloads are transient."
    )


class ResearchExport(Model):
    schema_version: Literal["1.0"] = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processing_scope: Literal["policy_approved_evidence_only"] = "policy_approved_evidence_only"
    report: RunReport
    omissions: ExportOmissions


def build_export(report: RunReport, policy: PolicyGate) -> ResearchExport:
    durable = durable_report(report, policy)
    return ResearchExport(
        report=durable,
        omissions=ExportOmissions(
            web_topics=sorted(
                {c.topic for c in report.result.coverage
                 if c.channel in {"web", "fact_checker"} and c.provider != "tavily_search"}
            ),
            evidence_count=len(report.result.evidence) - len(durable.result.evidence),
            observation_count=len(report.result.observations) - len(durable.result.observations),
        ),
    )


def write_export(path: str, report: RunReport, policy: PolicyGate) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_export(report, policy).model_dump_json(indent=2) + "\n")
