from datetime import UTC, date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, model_validator


def identifier() -> str:
    return str(uuid4())


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Topic = Literal[
    "neighborhood_discussion",
    "restaurant_reviews",
    "hoa_governance",
    "local_government",
    "amenities",
    "road_projects",
]


class PropertyCase(Model):
    id: str = Field(default_factory=identifier)
    address: str = Field(min_length=5, max_length=200)
    geography: str = Field(min_length=3, max_length=120)
    parcel_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,40}$")
    priorities: list[Topic] = Field(
        default_factory=lambda: ["neighborhood_discussion"], max_length=5
    )
    as_of: date = Field(default_factory=date.today)


class Evidence(Model):
    id: str = Field(default_factory=identifier)
    provider: str
    uri: HttpUrl
    title: str
    excerpt: str = Field(max_length=1000)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    retention: Literal["persistent", "ephemeral"]
    kind: Literal["official_record", "user_document", "reported", "synthetic"]
    record_id: str | None = None
    source_updated_at: str | None = None
    record_date: str | None = None
    attribution: str | None = None
    match_method: str | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class Observation(Model):
    id: str = Field(default_factory=identifier)
    topic: str
    statement: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(min_length=1)
    location_scope: str
    observed_on: date
    qualifier: Literal["official_record", "reported", "question", "synthetic"]
    confidence: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)


class ParcelCandidate(Model):
    parcel_id: str
    address: str
    property_use: str
    assessed_value: str | None = None
    lot_area: str | None = None
    source_url: HttpUrl


class Coverage(Model):
    channel: str
    provider: str | None = None
    topic: str
    status: Literal[
        "complete", "attempted", "blocked", "empty", "truncated", "error", "not_implemented"
    ]
    reason: str
    queries_run: int = Field(default=0, ge=0)
    sources_returned: int = Field(default=0, ge=0)
    parcel_candidates: list[ParcelCandidate] = Field(default_factory=list, max_length=20)


class WebCitation(Model):
    evidence_id: str
    excerpt: str = Field(min_length=1, max_length=1000)


class WebFinding(Model):
    id: str = Field(default_factory=identifier)
    title: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=700)
    kind: Literal["reported_fact", "opinion", "mixed"]
    assessment: Literal["reported", "support_found", "conflicting", "unresolved"] = "reported"
    explanation: str = Field(default="", max_length=700)
    location_relevance: str = Field(default="", max_length=300)
    citations: list[WebCitation] = Field(min_length=1, max_length=5)


class BriefParagraph(Model):
    text: str = Field(min_length=1, max_length=2200)
    citations: list[WebCitation] = Field(min_length=1, max_length=8)


class BriefSection(Model):
    heading: str = Field(min_length=1, max_length=120)
    paragraphs: list[BriefParagraph] = Field(min_length=1, max_length=5)


class ResearchBrief(Model):
    overview: BriefParagraph
    sections: list[BriefSection] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=5)
    model: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WebResearch(Model):
    topic: str
    summary: str = Field(default="", max_length=1200)
    findings: list[WebFinding] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=12)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=5)
    queries: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    search_calls: int = 0
    usage_credits: float = 0
    review_completed: bool = False
    brief: ResearchBrief | None = None
    synthesis_status: Literal["not_run", "complete", "error"] = "not_run"


class ChannelResult(Model):
    observations: list[Observation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    coverage: list[Coverage] = Field(default_factory=list)
    research: list[WebResearch] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_provenance(self):
        ids = [e.id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate evidence IDs")
        if any(not set(o.evidence_ids) <= set(ids) for o in self.observations):
            raise ValueError("Observation references missing evidence")
        for research in self.research:
            if not set(research.evidence_ids) <= set(ids):
                raise ValueError("Research references missing evidence")
            if any(c.evidence_id not in research.evidence_ids
                   for f in research.findings for c in f.citations):
                raise ValueError("Finding references missing research source")
            if research.brief:
                paragraphs = [research.brief.overview] + [
                    p for section in research.brief.sections for p in section.paragraphs
                ]
                if any(c.evidence_id not in research.evidence_ids
                       for p in paragraphs for c in p.citations):
                    raise ValueError("Brief references missing research source")
        return self


class Claim(Model):
    statement: str
    observation_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    qualifier: str
    flags: list[str] = Field(default_factory=list)


class ResearchQuerySpec(Model):
    topic: Topic
    geography: str = Field(min_length=3, max_length=120)
    start_date: date
    end_date: date
    source_types: list[Literal["discussion", "official", "news", "reviews"]] = Field(
        min_length=1, max_length=4
    )
    # Search guidance within one Gemini request, not an application-call budget.
    max_queries: Literal[1, 2, 3] = 3
    address_anchor: str | None = Field(default=None, max_length=200)
    radius_meters: int = Field(default=1000, ge=100, le=5000)

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("Inverted date window")
        return self


class ResearchPlan(Model):
    channels: list[Literal["apis", "listing", "web"]] = Field(min_length=1, max_length=3)
    queries: list[ResearchQuerySpec] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def coherent_plan(self):
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("Duplicate channels")
        if self.queries and "web" not in self.channels:
            raise ValueError("Queries require web channel")
        return self


class FactCheckPlan(Model):
    topic: Topic
    geography: str
    checks: list[
        Literal[
            "location",
            "dates",
            "independent_sources",
            "contradictions",
            "opinion_vs_fact",
            "restaurant_identity",
            "distance",
            "review_freshness",
        ]
    ] = Field(min_length=3, max_length=8)
    max_queries: Literal[1, 2, 3] = 3


class GroundingChunk(Model):
    uri: HttpUrl | None = None
    title: str = ""


class GroundingSupport(Model):
    text: str
    chunk_indices: list[int]
    start_index: int = 0
    end_index: int = 0


class GroundedResponse(Model):
    provider: Literal["gemini_search", "synthetic_web"]
    text: str
    chunks: list[GroundingChunk] = Field(default_factory=list)
    supports: list[GroundingSupport] = Field(default_factory=list)
    search_entry_point: str = ""
    search_queries: list[str] = Field(default_factory=list)
    truncated: bool = False


class ExtractionCandidate(Model):
    topic: Topic
    statement: str = Field(min_length=1, max_length=500)
    support_indices: list[int] = Field(min_length=1)
    location_scope: str
    observed_on: date
    confidence: float = Field(ge=0, le=1)


class Extraction(Model):
    observations: list[ExtractionCandidate] = Field(default_factory=list, max_length=20)


class RunReport(Model):
    id: str = Field(default_factory=identifier)
    case: PropertyCase
    plan: ResearchPlan | None = None
    result: ChannelResult
    claims: list[Claim] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    demo: bool = False
