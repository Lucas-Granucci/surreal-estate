from importlib.resources import files
from urllib.parse import urlsplit

import yaml

from surreal_estate.models import (
    Evidence,
    FactCheckPlan,
    PropertyCase,
    ResearchPlan,
    ResearchQuerySpec,
)


class PolicyDenied(ValueError):
    pass


class PolicyGate:
    def __init__(self):
        self.rules = yaml.safe_load(
            files("surreal_estate.policy").joinpath("source_policies.yaml").read_text()
        )

    def require(self, provider: str, *, extraction: bool = False, refinement: bool = False):
        rule = self.rules.get(provider)
        if not rule or not rule["enabled"]:
            raise PolicyDenied("Source is not enabled")
        if extraction and not rule["extract"]:
            raise PolicyDenied("Source does not permit downstream extraction")
        if refinement and not rule.get("refine_with_same_provider", False):
            raise PolicyDenied("Source does not permit same-provider refinement")
        return rule

    def query(self, spec: ResearchQuerySpec, case: PropertyCase):
        if spec.geography.casefold().strip() != case.geography.casefold().strip():
            raise PolicyDenied("Query geography differs from case")
        if spec.end_date > case.as_of or spec.topic not in case.priorities:
            raise PolicyDenied("Query exceeds date or topic scope")
        if spec.topic not in {"neighborhood_discussion", "restaurant_reviews"}:
            raise PolicyDenied("Specialist not implemented")
        expected = {"reviews"} if spec.topic == "restaurant_reviews" else {"discussion"}
        if set(spec.source_types) != expected:
            raise PolicyDenied("Source types do not match specialist")
        if spec.topic == "restaurant_reviews" and spec.address_anchor != case.address:
            raise PolicyDenied("Restaurant queries must use the exact property address")
        if spec.address_anchor is not None and spec.address_anchor != case.address:
            raise PolicyDenied("Address anchor differs from case")

    def plan(self, plan: ResearchPlan, case: PropertyCase, max_calls: int):
        # Each spec dispatches one API call; internal search guidance is separate.
        if len(plan.queries) > max_calls:
            raise PolicyDenied("Plan exceeds grounded-call budget")
        keys = [q.model_dump_json() for q in plan.queries]
        if len(keys) != len(set(keys)):
            raise PolicyDenied("Duplicate query specs")
        for query in plan.queries:
            self.query(query, case)

    def persistable(self, evidence: Evidence) -> bool:
        rule = self.rules.get(evidence.provider)
        from surreal_estate.llm.tavily import public_url
        return bool(
            rule
            and rule["enabled"]
            and rule["retention"] == "persistent"
            and evidence.retention == "persistent"
            and (urlsplit(str(evidence.uri)).hostname in rule["hosts"]
                 or (rule.get("public_web") and public_url(str(evidence.uri))))
        )

    @staticmethod
    def required_factcheck_checks(spec: ResearchQuerySpec) -> list[str]:
        required = ["location", "dates", "independent_sources", "contradictions", "opinion_vs_fact"]
        if spec.topic == "restaurant_reviews":
            required += ["restaurant_identity", "distance", "review_freshness"]
        return required

    def factcheck(self, plan: FactCheckPlan, spec: ResearchQuerySpec, case: PropertyCase):
        self.query(spec, case)
        if plan.topic != spec.topic or plan.geography != spec.geography:
            raise PolicyDenied("Fact-check scope differs from approved research query")
        if not set(self.required_factcheck_checks(spec)) <= set(plan.checks) or len(
            plan.checks
        ) != len(set(plan.checks)):
            raise PolicyDenied("Fact-check plan is missing required checks or contains duplicates")
