"""
LLM evaluator — turns a provider completion into a validated AgentResult, and
falls back to the deterministic evaluator on ANY failure (call, parse, validate).

Contracts are unchanged: the validated LLM output maps into the existing
`AgentResult` / `Evidence` / `SourceRef`. Nothing here imports a concrete
provider — it depends only on the `LLMProvider` port and receives the provider by
injection, so no evaluator knows which vendor is in use.
"""
from __future__ import annotations

import json
import re
from typing import Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError

from oliver_core.prompts import build_messages
from oliver_core.providers.base import (
    CompletionOptions,
    LLMProvider,
    Message,
    ProviderError,
)
from oliver_core.schemas import AgentResult, Evidence, SourceRef, SubmissionCreate

# The deterministic evaluator signature (the fallback + prompt source of truth).
Evaluator = Callable[[SubmissionCreate], Awaitable[tuple]]

# Failure modes that must degrade to the deterministic evaluator.
_FALLBACK_ERRORS = (ProviderError, ValidationError, ValueError, TimeoutError)


class _LLMEvidence(BaseModel):
    model_config = {"extra": "ignore"}
    claim: str
    excerpt: str = ""
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class LLMDimensionOutput(BaseModel):
    """Strict validation of the model's JSON before anything enters the system.
    Extra keys are ignored; out-of-range or missing required fields raise, which
    triggers the deterministic fallback."""
    model_config = {"extra": "ignore"}

    value: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = ""
    evidence: list[_LLMEvidence] = []
    gaps: list[str] = []
    reasoning: str = ""

    def to_agent_result(
        self, *, agent: str, dimension: str, dimension_label: str
    ) -> AgentResult:
        evidence = [
            Evidence(
                claim=e.claim,
                source_ref=SourceRef(
                    kind="submission_span", locator=(e.excerpt[:120] or "llm")
                ),
                confidence=e.confidence,
            )
            for e in self.evidence
        ]
        return AgentResult(
            agent=agent, dimension=dimension, dimension_label=dimension_label,
            value=self.value, confidence=self.confidence, summary=self.summary,
            evidence=evidence, gaps=self.gaps, reasoning=self.reasoning,
            scored_by="llm",
        )


def _first_json_object(text: str) -> str | None:
    """Return the first balanced {...} block, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> dict:
    """Tolerant JSON extraction: handle code fences and surrounding prose.
    Raises ValueError when no JSON object can be recovered (→ fallback)."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        block = _first_json_object(text)
        if block is None:
            raise ValueError("no JSON object found in LLM response")
        obj = json.loads(block)          # may raise json.JSONDecodeError → caught upstream
    if not isinstance(obj, dict):
        raise ValueError("LLM response JSON is not an object")
    return obj


async def _fallback(
    evaluator: Evaluator, sub: SubmissionCreate, *, agent, dimension, dimension_label
) -> AgentResult:
    value, conf, summary, evidence, gaps = await evaluator(sub)
    return AgentResult(
        agent=agent, dimension=dimension, dimension_label=dimension_label,
        value=value, confidence=conf, summary=summary,
        evidence=evidence, gaps=gaps, scored_by="llm-fallback",
    )


def make_llm_agent(
    provider: LLMProvider,
    evaluator: Evaluator,
    agent: str,
    dimension: str,
    dimension_label: str,
    *,
    options: CompletionOptions | None = None,
):
    """Build an Agent (AgentContext -> AgentResult) for one dimension that scores
    via the LLM and falls back to `evaluator` on any failure."""
    opts = options or CompletionOptions(temperature=0.0, json_mode=True, max_tokens=900)

    async def _agent(ctx) -> AgentResult:
        try:
            messages: list[Message] = build_messages(dimension, ctx.submission)
            completion = await provider.complete(messages, options=opts)
            data = extract_json(completion.text)
            validated = LLMDimensionOutput.model_validate(data)
            return validated.to_agent_result(
                agent=agent, dimension=dimension, dimension_label=dimension_label
            )
        except _FALLBACK_ERRORS:
            # Anticipated failures: call error, unparseable/invalid JSON, schema
            # violation. json.JSONDecodeError is a ValueError, so it is covered.
            return await _fallback(
                evaluator, ctx.submission,
                agent=agent, dimension=dimension, dimension_label=dimension_label,
            )
        except Exception:  # noqa: BLE001 — production safety net
            # An unexpected error must never fail the whole assessment: degrade this
            # one dimension to the deterministic evaluator. (Bugs still surface via
            # scored_by="llm-fallback" on a dimension the LLM should have scored.)
            return await _fallback(
                evaluator, ctx.submission,
                agent=agent, dimension=dimension, dimension_label=dimension_label,
            )

    _agent.__name__ = f"{agent.lower()}_llm_agent"
    return _agent
