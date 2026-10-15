from datetime import timedelta
from importlib.resources import files

from surreal_estate.models import (
    ChannelResult,
    Coverage,
    Extraction,
    ExtractionCandidate,
    GroundedResponse,
    GroundingChunk,
    GroundingSupport,
    PropertyCase,
    ResearchPlan,
    ResearchQuerySpec,
)


def fixture_case():
    return PropertyCase.model_validate_json(
        files("surreal_estate.evals").joinpath("pittsburgh.json").read_text()
    )


class FixturePlanner:
    async def plan(self, case, ctx):
        return ResearchPlan(
            channels=["apis", "listing", "web"],
            queries=[
                ResearchQuerySpec(
                    topic="neighborhood_discussion",
                    geography=case.geography,
                    address_anchor=case.address,
                    start_date=case.as_of - timedelta(days=365),
                    end_date=case.as_of,
                    source_types=["discussion"],
                )
            ],
        )


class FixtureAPI:
    name = "apis"

    async def run(self, case, ctx):
        return ChannelResult(
            coverage=[
                Coverage(
                    channel=self.name,
                    topic="geocoding",
                    status="blocked",
                    reason="Offline demo: live Census request disabled",
                )
            ]
        )


class FixtureSearch:
    provider = "synthetic_web"

    async def search(self, spec, ctx):
        ctx.reserve("web_search")
        text = f"Synthetic discussion dated {spec.end_date} in {spec.geography} reported temporary sidewalk work."
        return GroundedResponse(
            provider=self.provider,
            text=text,
            chunks=[
                GroundingChunk(
                    uri="https://example.org/synthetic-discussion",
                    title="Synthetic evaluation fixture",
                )
            ],
            supports=[GroundingSupport(text=text, chunk_indices=[0], end_index=len(text))],
        )


class FixtureExtractor:
    async def extract(self, spec, response, ctx):
        return Extraction(
            observations=[
                ExtractionCandidate(
                    topic=spec.topic,
                    statement=response.text,
                    support_indices=[0],
                    location_scope=spec.geography,
                    observed_on=spec.end_date,
                    confidence=1,
                )
            ]
        )
