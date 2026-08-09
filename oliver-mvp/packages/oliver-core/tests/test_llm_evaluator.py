"""LLM evaluator — JSON validation, mapping into AgentResult, and fallback."""
import asyncio

import pytest
from pydantic import ValidationError

from oliver_core.llm_evaluator import (
    LLMDimensionOutput,
    extract_json,
    make_llm_agent,
)
from oliver_core.mock_assessor import AgentContext, mock_doc_guard
from oliver_core.schemas import AgentResult, Evidence

AGENT_ARGS = dict(agent="DocGuard", dimension="ideaCompleteness", dimension_label="Idea Completeness")


# ── JSON extraction ────────────────────────────────────────────────────────

def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_from_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_from_prose_wrapping():
    assert extract_json('Sure! Here it is: {"a": 1, "b": {"c": 2}} — hope that helps') == {"a": 1, "b": {"c": 2}}


def test_extract_garbage_raises():
    with pytest.raises(ValueError):
        extract_json("no json here at all")


def test_extract_non_object_raises():
    with pytest.raises(ValueError):
        extract_json("[1, 2, 3]")


# ── Pydantic validation ────────────────────────────────────────────────────

def test_valid_output_parses_and_ignores_extra():
    out = LLMDimensionOutput.model_validate(
        {"value": 80, "confidence": 0.7, "summary": "ok", "extra_key": "ignored",
         "evidence": [{"claim": "x", "excerpt": "y", "confidence": 0.6}], "gaps": ["z"]}
    )
    assert out.value == 80 and out.confidence == 0.7


@pytest.mark.parametrize("bad", [
    {"confidence": 0.5},                                  # missing value
    {"value": 80},                                        # missing confidence
    {"value": 150, "confidence": 0.5},                    # value out of range
    {"value": 80, "confidence": 2.0},                     # confidence out of range
])
def test_invalid_output_raises(bad):
    with pytest.raises(ValidationError):
        LLMDimensionOutput.model_validate(bad)


def test_to_agent_result_maps_typed_evidence():
    out = LLMDimensionOutput.model_validate(
        {"value": 80, "confidence": 0.7, "summary": "ok",
         "evidence": [{"claim": "quantified", "excerpt": "2M EUR", "confidence": 0.9}], "gaps": []}
    )
    r = out.to_agent_result(**AGENT_ARGS)
    assert isinstance(r, AgentResult) and r.scored_by == "llm"
    assert isinstance(r.evidence[0], Evidence)
    assert r.evidence[0].source_ref.kind == "submission_span"
    assert r.evidence[0].source_ref.locator == "2M EUR"


# ── Agent success + fallback ───────────────────────────────────────────────

def test_llm_agent_success(valid_provider, strong_sub):
    agent = make_llm_agent(valid_provider, mock_doc_guard, **AGENT_ARGS)
    r = asyncio.run(agent(AgentContext(submission=strong_sub)))
    assert r.scored_by == "llm" and r.value == 82


def test_fallback_on_provider_failure(failing_provider, strong_sub):
    agent = make_llm_agent(failing_provider, mock_doc_guard, **AGENT_ARGS)
    r = asyncio.run(agent(AgentContext(submission=strong_sub)))
    assert r.scored_by == "llm-fallback"
    # fallback == the deterministic evaluator's own output
    dv, dc, *_ = asyncio.run(mock_doc_guard(strong_sub))
    assert r.value == dv and r.confidence == dc


def test_fallback_on_bad_json(make_stub, strong_sub):
    agent = make_llm_agent(make_stub("not json"), mock_doc_guard, **AGENT_ARGS)
    r = asyncio.run(agent(AgentContext(submission=strong_sub)))
    assert r.scored_by == "llm-fallback"


def test_fallback_on_invalid_schema(make_stub, strong_sub):
    agent = make_llm_agent(make_stub('{"value": 999}'), mock_doc_guard, **AGENT_ARGS)
    r = asyncio.run(agent(AgentContext(submission=strong_sub)))
    assert r.scored_by == "llm-fallback"
