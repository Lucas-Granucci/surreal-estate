"""Transient user-display transport, distinct from durable downstream exports."""

from pathlib import Path
from typing import Literal

from surreal_estate.models import GroundedResponse, Model, RunReport
from surreal_estate.orchestrator.runner import RunOutcome


class WebDisplayResult(Model):
    topic: str
    stage: str
    label: Literal["model_reported_summary", "model_assessment"]
    response: GroundedResponse


class FrontendResponse(Model):
    schema_version: Literal["1.0"] = "1.0"
    purpose: Literal["user_display"] = "user_display"
    retention: Literal["ephemeral"] = "ephemeral"
    report: RunReport
    web: list[WebDisplayResult]


class DevelopmentSnapshot(FrontendResponse):
    """Local display-debugging copy; never mislabeled as ephemeral transport."""

    purpose: Literal["development_debug"] = "development_debug"
    retention: Literal["development_file"] = "development_file"


def save_development_snapshot(
    outcome: RunOutcome, directory: str = "exports", *, path: str | None = None
) -> Path:
    snapshot = DevelopmentSnapshot.model_validate(
        {
            **build_frontend_response(outcome).model_dump(mode="json"),
            "purpose": "development_debug",
            "retention": "development_file",
        }
    )
    target = Path(path) if path else Path(directory) / (outcome.report.id + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Default paths preserve each run; an explicit output path replaces its prior contents.
    with target.open("w" if path else "x", encoding="utf-8") as output:
        output.write(snapshot.model_dump_json(indent=2) + "\n")
    return target


def build_frontend_response(outcome: RunOutcome) -> FrontendResponse:
    """Preserve provider text, citation indexing and suggestions without extraction."""
    return FrontendResponse(
        report=outcome.report.model_copy(update={"trace": []}),
        web=[
            WebDisplayResult(
                topic=display.topic,
                stage=display.stage,
                label="model_assessment"
                if display.stage.startswith("Claim re-check")
                else "model_reported_summary",
                response=display.response,
            )
            for display in outcome.displays
        ],
    )
