import time
from dataclasses import dataclass, field

from pydantic import Field

from surreal_estate.models import Model
from surreal_estate.orchestrator.debug import DebugLog
from surreal_estate.policy.gate import PolicyGate


class BudgetExceeded(RuntimeError):
    pass


class Budget(Model):
    max_grounded_calls: int = Field(default=2, ge=0, le=5)
    max_factcheck_calls: int = Field(default=2, ge=0, le=5)
    max_llm_calls: int = Field(default=8, ge=1, le=12)
    max_web_search_calls: int = Field(default=6, ge=0, le=12)
    max_synthesis_calls: int = Field(default=4, ge=0, le=5)
    max_api_calls: int = Field(default=12, ge=0, le=32)
    output_tokens_per_call: int = Field(default=4096, ge=128, le=8192)
    grounded_output_tokens_per_call: int = Field(default=4096, ge=128, le=8192)
    deadline_seconds: float = Field(default=180, gt=0, le=600)
    request_seconds: float = Field(default=60, gt=0, le=180)


@dataclass
class RunContext:
    debug: DebugLog = field(default_factory=DebugLog)
    budget: Budget = field(default_factory=Budget)
    policy: PolicyGate = field(default_factory=PolicyGate)
    trace: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    confirmed_geocode: tuple[dict, str] | None = None
    started: float = field(default_factory=time.monotonic)

    @property
    def remaining(self):
        return max(0.0, self.budget.deadline_seconds - (time.monotonic() - self.started))

    def reserve(self, kind: str) -> float:
        limits = {
            "llm": self.budget.max_llm_calls,
            "grounded": self.budget.max_grounded_calls,
            "factcheck": self.budget.max_factcheck_calls,
            "api": self.budget.max_api_calls,
            "web_search": self.budget.max_web_search_calls,
            "synthesis": self.budget.max_synthesis_calls,
        }
        if self.remaining <= 0 or self.counts.get(kind, 0) >= limits[kind]:
            raise BudgetExceeded("Run deadline or call budget exhausted")
        self.counts[kind] = self.counts.get(kind, 0) + 1
        self.trace.append(f"call:{kind}:{self.counts[kind]}")
        return min(self.remaining, self.budget.request_seconds)
