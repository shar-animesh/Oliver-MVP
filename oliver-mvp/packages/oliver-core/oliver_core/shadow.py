"""
Shadow comparison — run the deterministic and LLM evaluators on the SAME
submission and diff them, without persisting anything.

This is the validation harness for the LLM migration: before trusting LLM scoring
(and again whenever a new provider/model lands), run the corpus through
`shadow_compare` and inspect per-dimension deltas and gate agreement. It is
provider-agnostic — it takes an `LLMProvider` (the port), never a vendor.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from oliver_core.mock_assessor import AGENTS, AgentContext, build_llm_agents, consolidate
from oliver_core.schemas import SubmissionCreate


@dataclass(frozen=True)
class DimensionDelta:
    dimension: str
    rubric_value: int
    llm_value: int
    delta: int                 # llm - rubric
    llm_scored_by: str         # llm | llm-fallback


@dataclass(frozen=True)
class ShadowResult:
    deltas: list[DimensionDelta]
    rubric_gate: str
    llm_gate: str
    gate_agrees: bool
    max_abs_delta: int
    fell_back: list[str]       # dimensions where the LLM path degraded to the rubric


async def shadow_compare(sub: SubmissionCreate, provider) -> ShadowResult:
    ctx = AgentContext(submission=sub)
    rubric = list(await asyncio.gather(*(a(ctx) for a in AGENTS)))
    llm = list(await asyncio.gather(*(a(ctx) for a in build_llm_agents(provider))))

    r_by = {x.dimension: x for x in rubric}
    l_by = {x.dimension: x for x in llm}
    deltas = [
        DimensionDelta(
            dimension=d,
            rubric_value=r_by[d].value,
            llm_value=l_by[d].value,
            delta=l_by[d].value - r_by[d].value,
            llm_scored_by=l_by[d].scored_by,
        )
        for d in r_by
    ]

    _, r_verdict, _ = consolidate(rubric, sub.current_stage.value)
    _, l_verdict, _ = consolidate(llm, sub.current_stage.value)
    rg, lg = r_verdict.gate_decision.value, l_verdict.gate_decision.value

    return ShadowResult(
        deltas=deltas,
        rubric_gate=rg,
        llm_gate=lg,
        gate_agrees=(rg == lg),
        max_abs_delta=max((abs(x.delta) for x in deltas), default=0),
        fell_back=[x.dimension for x in deltas if x.llm_scored_by == "llm-fallback"],
    )
