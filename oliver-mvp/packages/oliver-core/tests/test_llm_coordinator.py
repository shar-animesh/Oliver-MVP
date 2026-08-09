"""
LLM coordinator + end-to-end: agent selection, provenance, narrator on the port,
shadow comparison, backward compatibility, and isolation.
"""
import asyncio
import subprocess
import sys

import pytest

from oliver_core.mock_assessor import AGENTS, assess_submission, resolve_agents
from oliver_core.prompts import PROMPT_VERSION
from oliver_core.shadow import shadow_compare


# ── Agent selection ────────────────────────────────────────────────────────

def test_default_is_deterministic(monkeypatch):
    monkeypatch.delenv("OLIVER_AGENTS", raising=False)
    agents, mode, provider = resolve_agents()
    assert mode == "rubric" and provider is None and agents == AGENTS


def test_llm_mode_without_provider_degrades(monkeypatch):
    monkeypatch.setenv("OLIVER_AGENTS", "llm")
    monkeypatch.setattr("oliver_core.mock_assessor.get_provider", lambda: None)
    _, mode, provider = resolve_agents()
    assert mode == "rubric" and provider is None      # graceful degrade


def test_llm_mode_with_provider_selects_llm(monkeypatch, valid_provider):
    monkeypatch.setenv("OLIVER_AGENTS", "llm")
    agents, mode, provider = resolve_agents(provider=valid_provider)
    assert mode == "llm" and provider is valid_provider and len(agents) == len(AGENTS)


# ── End-to-end assessment ──────────────────────────────────────────────────

def test_e2e_llm_assessment_sets_provenance(monkeypatch, valid_provider, strong_sub):
    monkeypatch.setenv("OLIVER_AGENTS", "llm")
    monkeypatch.setattr("oliver_core.mock_assessor.get_provider", lambda: valid_provider)
    a = asyncio.run(assess_submission(strong_sub))
    assert {d.scored_by for d in a.dimensions} == {"llm"}
    assert a.provenance is not None
    assert a.provenance.provider == "stub"
    assert a.provenance.model == "stub-model"
    assert a.provenance.prompt_version == PROMPT_VERSION
    assert a.verdict.gate_decision.value in {"GATE_PASS", "NO_GO_RECOMMENDED", "COACHING_REJECT"}


def test_e2e_llm_failure_degrades_per_dimension(monkeypatch, failing_provider, strong_sub):
    monkeypatch.setenv("OLIVER_AGENTS", "llm")
    monkeypatch.setattr("oliver_core.mock_assessor.get_provider", lambda: failing_provider)
    a = asyncio.run(assess_submission(strong_sub))
    assert {d.scored_by for d in a.dimensions} == {"llm-fallback"}
    assert a.verdict.composite is not None            # still a valid assessment


def test_e2e_default_unchanged_and_no_provenance(monkeypatch, strong_sub):
    monkeypatch.delenv("OLIVER_AGENTS", raising=False)
    a = asyncio.run(assess_submission(strong_sub))
    assert {d.scored_by for d in a.dimensions} == {"rubric"}
    assert a.provenance is None                        # backward compatible


# ── Shadow comparison ──────────────────────────────────────────────────────

def test_shadow_compare_runs(valid_provider, strong_sub):
    res = asyncio.run(shadow_compare(strong_sub, valid_provider))
    assert len(res.deltas) == len(AGENTS)
    assert res.rubric_gate and res.llm_gate
    assert isinstance(res.gate_agrees, bool)
    assert res.fell_back == []                          # stub succeeds on every dimension


def test_shadow_reports_fallback(failing_provider, strong_sub):
    res = asyncio.run(shadow_compare(strong_sub, failing_provider))
    assert len(res.fell_back) == len(AGENTS)            # all dimensions fell back


# ── Narrator on the provider port ──────────────────────────────────────────

def test_narrator_default_is_template(monkeypatch, strong_sub):
    monkeypatch.delenv("OLIVER_NARRATIVE", raising=False)
    a = asyncio.run(assess_submission(strong_sub))
    assert a.narrative.generated_by == "template"


def test_narrator_llm_uses_provider(monkeypatch, strong_sub):
    # A schema-valid AssessmentNarrative payload (only executive_summary needed;
    # all other fields default). No numbers -> passes the grounding guard.
    narration = '{"executive_summary": "A strong pilot idea targeting turbine downtime."}'

    class NarrateProvider:
        name = "stub"; model = "stub-model"
        async def complete(self, messages, *, options=None):
            from oliver_core.providers.base import Completion
            return Completion(text=narration, model="stub-model")

    monkeypatch.setenv("OLIVER_NARRATIVE", "llm")
    # The narrator resolves its provider via narrative.get_provider.
    monkeypatch.setattr("oliver_core.narrative.get_provider", lambda: NarrateProvider())
    a = asyncio.run(assess_submission(strong_sub))
    assert a.narrative.generated_by == "llm"


def test_narrator_llm_falls_back_on_failure(monkeypatch, failing_provider, strong_sub):
    monkeypatch.setenv("OLIVER_NARRATIVE", "llm")
    monkeypatch.setattr("oliver_core.narrative.get_provider", lambda: failing_provider)
    a = asyncio.run(assess_submission(strong_sub))
    assert a.narrative.generated_by == "llm-fallback"   # provider failed -> template


# ── Backward compatibility ─────────────────────────────────────────────────

def test_assessment_without_provenance_is_valid():
    from oliver_core.schemas import Assessment, VerdictResult, StageAssignment, CoachingNote, GateDecision, DIStage, LifecycleState
    a = Assessment(
        dimensions=[], verdict=VerdictResult(gate_decision=GateDecision.GATE_PASS),
        stage=StageAssignment(assigned_stage=DIStage.DI1, lifecycle_state=LifecycleState.SENSED, rationale="x"),
        coaching=CoachingNote(message="x"),
    )
    assert a.provenance is None                          # optional, defaults None
    assert "provenance" in a.model_dump()                # serialized (as null)


# ── Isolation: coordinator/evaluator/narrator never import Ollama ──────────

def _imports_ollama(stmt: str) -> bool:
    code = f"import sys; {stmt}; sys.exit(1 if 'oliver_core.providers.ollama' in sys.modules else 0)"
    return subprocess.run([sys.executable, "-c", code]).returncode == 1


def test_llm_stack_import_does_not_load_ollama():
    assert not _imports_ollama(
        "import oliver_core.mock_assessor, oliver_core.llm_evaluator, "
        "oliver_core.prompts, oliver_core.narrative, oliver_core.shadow"
    )
