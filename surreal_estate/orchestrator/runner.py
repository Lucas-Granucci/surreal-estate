import asyncio
from dataclasses import dataclass, field

import httpx
from pydantic import ValidationError

from surreal_estate.channels.listing.channel import ListingChannel
from surreal_estate.channels.web.channel import LiveDisplay, WebChannel
from surreal_estate.errors import failure_reason
from surreal_estate.models import ChannelResult, Coverage, PropertyCase, RunReport
from surreal_estate.orchestrator.context import BudgetExceeded, RunContext
from surreal_estate.orchestrator.debug import DebugEvent
from surreal_estate.policy.gate import PolicyDenied
from surreal_estate.synthesis.dossier import synthesize

EXPECTED_ERRORS = (
    httpx.HTTPError,
    ValidationError,
    ValueError,
    KeyError,
    TypeError,
    TimeoutError,
    BudgetExceeded,
)


@dataclass
class RunOutcome:
    report: RunReport
    displays: list[LiveDisplay]
    debug_events: list[DebugEvent] = field(default_factory=list)
    snapshot_path: str | None = None


async def run(
    case: PropertyCase,
    ctx: RunContext,
    planner,
    api_channel,
    *,
    search=None,
    extractor=None,
    fact_checker=None,
    demo=False,
) -> RunOutcome:
    results, displays = [], []
    plan = None
    # Fixed, policy-gated public adapters are a baseline, independent of model choices.
    api_ran = getattr(api_channel, "default_enabled", False)
    if api_ran:
        ctx.trace.append("channel:apis:started")
        try:
            async with asyncio.timeout(ctx.remaining):
                results.append(await api_channel.run(case, ctx))
        except EXPECTED_ERRORS as exc:
            results.append(api_channel.partial_result)
            results.append(
                ChannelResult(
                    coverage=[
                        Coverage(
                            channel="apis",
                            topic="research",
                            status="truncated",
                            reason=f"Structured research stopped ({failure_reason(exc)}); completed sources retained",
                        )
                    ]
                )
            )
        ctx.trace.append("channel:apis:finished")
    try:
        async with asyncio.timeout(ctx.remaining):
            ctx.trace.append("planner:started")
            plan = await planner.plan(case, ctx)
            if api_ran:
                plan = plan.model_copy(
                    update={"channels": ["apis", *(c for c in plan.channels if c != "apis")]}
                )
            event = ctx.debug.begin(
                "Policy gate",
                {
                    "case": case.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                    "budget": ctx.budget.model_dump(),
                },
            )
            try:
                ctx.policy.plan(plan, case, ctx.budget.max_grounded_calls)
            except PolicyDenied as exc:
                ctx.debug.finish(
                    event, parsed={"decision": "blocked", "reason": str(exc)}, error=exc
                )
                raise
            ctx.debug.finish(
                event, parsed={"decision": "allowed", "execution_order": plan.channels}
            )
            ctx.trace.append("planner:validated")
    except EXPECTED_ERRORS as exc:
        plan = None
        # Do not stringify HTTP/model exceptions: they can contain credentials or content.
        results.append(
            ChannelResult(
                coverage=[
                    Coverage(
                        channel="planner",
                        topic="plan",
                        status="blocked" if isinstance(exc, PolicyDenied) else "error",
                        reason=f"Planning failed closed ({failure_reason(exc)})",
                    )
                ]
            )
        )
    if plan is not None:
        channels = {"apis": api_channel, "listing": ListingChannel()}
        if search is not None:
            channels["web"] = WebChannel(plan.queries, search, extractor, fact_checker)
        for name in plan.channels:
            if name == "apis" and api_ran:
                continue
            if name not in channels:
                results.append(
                    ChannelResult(
                        coverage=[
                            Coverage(
                                channel=name,
                                topic="research",
                                status="blocked",
                                reason="Channel not enabled for this run",
                            )
                        ]
                    )
                )
                continue
            ctx.trace.append(f"channel:{name}:started")
            channel = channels[name]
            try:
                async with asyncio.timeout(ctx.remaining):
                    results.append(await channel.run(case, ctx))
                ctx.trace.append(f"channel:{name}:finished")
            except EXPECTED_ERRORS as exc:
                results.append(
                    ChannelResult(
                        coverage=[
                            Coverage(
                                channel=name,
                                topic="research",
                                status="truncated"
                                if isinstance(exc, (TimeoutError, BudgetExceeded))
                                else "error",
                                provider=getattr(channel, "provider", None),
                                reason=f"Channel stopped ({failure_reason(exc)}); no unsupported findings added",
                            )
                        ]
                    )
                )
                ctx.trace.append(f"channel:{name}:stopped")
            if isinstance(channel, WebChannel):
                displays.extend(channel.displays)
        for name in {"apis", "listing", "web"} - set(plan.channels):
            results.append(
                ChannelResult(
                    coverage=[
                        Coverage(
                            channel=name,
                            topic="research",
                            status="blocked",
                            reason="Not selected by planner",
                        )
                    ]
                )
            )
        for topic in case.priorities:
            if topic not in {"neighborhood_discussion", "restaurant_reviews"}:
                results.append(
                    ChannelResult(
                        coverage=[
                            Coverage(
                                channel="web",
                                topic=topic,
                                status="not_implemented",
                                reason="Specialist not implemented",
                            )
                        ]
                    )
                )
            elif topic not in {query.topic for query in plan.queries}:
                results.append(
                    ChannelResult(
                        coverage=[
                            Coverage(
                                channel="web",
                                topic=topic,
                                status="blocked",
                                reason="Requested topic was not selected by the planner",
                            )
                        ]
                    )
                )
    result = ChannelResult(
        observations=[o for r in results for o in r.observations],
        evidence=[e for r in results for e in r.evidence],
        coverage=[c for r in results for c in r.coverage],
    )
    return RunOutcome(
        RunReport(
            case=case,
            plan=plan,
            result=result,
            claims=synthesize(result),
            trace=ctx.trace.copy(),
            demo=demo,
        ),
        displays,
        ctx.debug.events,
    )
