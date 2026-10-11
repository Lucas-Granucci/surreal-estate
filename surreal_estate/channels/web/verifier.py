import re

from surreal_estate.models import (
    ChannelResult,
    Coverage,
    Evidence,
    Extraction,
    GroundedResponse,
    Observation,
    ResearchQuerySpec,
)
from surreal_estate.policy.gate import PolicyGate

# A conservative fixture verifier, not a semantic truth or fair-housing classifier.
DISALLOWED = re.compile(
    r"\b(safe|unsafe|crime|schools?|residents say|race|racial|religion|ethnic|"
    r"demographic|structural|foundation|legal|illegal)\b|(?:u/|@)\w+",
    re.IGNORECASE,
)


def verify(
    spec: ResearchQuerySpec, response: GroundedResponse, extraction: Extraction, policy: PolicyGate
) -> ChannelResult:
    policy.require(response.provider, extraction=True)
    observations, evidence = [], []
    rejected = 0
    for item in extraction.observations:
        if (
            item.topic != spec.topic
            or item.location_scope.casefold() != spec.geography.casefold()
            or not spec.start_date <= item.observed_on <= spec.end_date
            or DISALLOWED.search(item.statement)
        ):
            rejected += 1
            continue
        indices = set(item.support_indices)
        if not indices or any(i < 0 or i >= len(response.supports) for i in indices):
            rejected += 1
            continue
        supports = [response.supports[i] for i in indices]
        # Require all fields in the same support segment; concatenating unrelated spans
        # could otherwise falsely attach a date/geography to another statement.
        relevant = [
            s
            for s in supports
            if item.statement in s.text
            and spec.geography.casefold() in s.text.casefold()
            and item.observed_on.isoformat() in s.text
            and s.text in response.text
        ]
        chunk_ids = {i for s in relevant for i in s.chunk_indices}
        if (
            not relevant
            or not chunk_ids
            or any(
                i < 0 or i >= len(response.chunks) or response.chunks[i].uri is None
                for i in chunk_ids
            )
        ):
            rejected += 1
            continue
        attached = [
            Evidence(
                provider=response.provider,
                uri=response.chunks[i].uri,
                title=response.chunks[i].title,
                excerpt=item.statement,
                retention=policy.require(response.provider)["retention"],
                kind="synthetic" if response.provider == "synthetic_web" else "reported",
            )
            for i in sorted(chunk_ids)
        ]
        evidence.extend(attached)
        observations.append(
            Observation(
                topic=item.topic,
                statement=item.statement,
                evidence_ids=[e.id for e in attached],
                location_scope=item.location_scope,
                observed_on=item.observed_on,
                qualifier="synthetic" if response.provider == "synthetic_web" else "reported",
                confidence=item.confidence,
                flags=["not_independently_verified"]
                + (["single_source"] if len({str(e.uri) for e in attached}) == 1 else []),
            )
        )
    return ChannelResult(
        observations=observations,
        evidence=evidence,
        coverage=[
            Coverage(
                channel="web",
                topic=spec.topic,
                status="truncated"
                if response.truncated
                else "complete"
                if observations
                else "empty",
                reason=f"{len(observations)} supported observations; {rejected} rejected",
                queries_run=1,
                sources_returned=sum(c.uri is not None for c in response.chunks),
            )
        ],
    )
