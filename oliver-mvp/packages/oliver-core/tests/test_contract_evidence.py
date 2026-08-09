"""
Increment 1 — agent + evidence contract.

Covers: the new typed contracts, the backward-compatible `evidence` projection
(so report/narrator/frontend are untouched), the forward-compatible LLM/RAG
contract (proving the next increment needs no contract change), and that
deterministic assessment behaviour is unchanged.
"""
import asyncio

import pytest

from oliver_core.schemas import (
    AgentResult,
    DimensionScore,
    Evidence,
    SourceRef,
    SubmissionCreate,
)
from oliver_core.mock_assessor import (
    AgentContext,
    DIMENSION_KEYS,
    assess_submission,
    consolidate,
)

STRONG = SubmissionCreate(
    title="Predictive maintenance for turbines",
    problem_statement=(
        "Unplanned turbine downtime costs about 2M EUR per year across the fleet. "
        "We want 48-hour advance failure warnings from vibration data."
    ),
    proposed_approach="Train a model on historical vibration data to flag anomalies.",
    expected_value="Avoid ~2M EUR/year in unplanned downtime; cut emergency call-outs.",
    data_sources="PI System vibration telemetry, maintenance logs.",
    sponsor="VP Gas Services",
    team_size=4,
)


# ── Typed contracts ───────────────────────────────────────────────────────

def test_sourceref_and_evidence_defaults():
    e = Evidence(claim="problem is quantified")
    assert e.source_ref.kind == "field"
    assert e.confidence == 1.0
    assert 0.0 <= e.confidence <= 1.0


def test_evidence_confidence_bounds():
    with pytest.raises(Exception):
        Evidence(claim="x", confidence=1.5)


def test_agent_result_defaults_and_typed_evidence():
    r = AgentResult(
        agent="DocGuard", dimension="ideaCompleteness", dimension_label="Idea Completeness",
        value=80, confidence=0.9,
        evidence=[Evidence(claim="problem present", source_ref=SourceRef(kind="field", locator="problem_present"))],
    )
    assert r.scored_by == "rubric"          # provenance default
    assert r.reasoning == ""
    assert isinstance(r.evidence[0], Evidence)


# ── Backward compatibility: computed projection ───────────────────────────

def test_dimension_evidence_is_string_projection():
    d = DimensionScore(
        agent="DocGuard", dimension="ideaCompleteness", dimension_label="Idea Completeness",
        value=80, confidence=0.9, weight=25, summary="ok",
        evidence_detail=[
            Evidence(claim="problem present — 'turbine downtime'"),
            Evidence(claim="sponsor named — 'VP Gas Services'"),
        ],
    )
    # legacy consumers read .evidence as list[str] and get the claims, in order
    assert d.evidence == ["problem present — 'turbine downtime'", "sponsor named — 'VP Gas Services'"]
    assert all(isinstance(x, str) for x in d.evidence)


def test_dimension_wire_shape_has_both_fields():
    d = DimensionScore(
        agent="DocGuard", dimension="ideaCompleteness", dimension_label="Idea Completeness",
        value=80, confidence=0.9, weight=25, summary="ok",
        evidence_detail=[Evidence(claim="c1")],
    )
    dumped = d.model_dump()
    assert dumped["evidence"] == ["c1"]                     # legacy string list on the wire
    assert dumped["evidence_detail"][0]["claim"] == "c1"   # typed detail on the wire
    assert dumped["scored_by"] == "rubric"


def test_dimension_legacy_evidence_rehydrates():
    # An old record / old caller passing evidence as list[str] still works.
    d = DimensionScore(
        agent="DocGuard", dimension="ideaCompleteness", dimension_label="Idea Completeness",
        value=80, confidence=0.9, weight=25, summary="ok",
        evidence=["legacy claim A", "legacy claim B"],
    )
    assert d.evidence == ["legacy claim A", "legacy claim B"]
    assert [e.claim for e in d.evidence_detail] == ["legacy claim A", "legacy claim B"]
    assert d.evidence_detail[0].source_ref.locator == "legacy"


# ── Forward compatibility: the LLM / RAG contract ─────────────────────────

def _llm_results():
    """A full set of AgentResults as an LLM/RAG agent would emit them —
    scored_by='llm', evidence grounded in a retrieved document."""
    labels = {
        "ideaCompleteness": "Idea Completeness", "ideaQuality": "Idea Quality",
        "strategicValue": "Strategic / Business Value",
        "technicalFeasibility": "Technical Feasibility",
        "executionReadiness": "Execution Readiness",
    }
    return [
        AgentResult(
            agent="LLM", dimension=k, dimension_label=labels[k],
            value=75, confidence=0.8, summary="llm judged",
            evidence=[Evidence(
                claim="grounded in prior pilot",
                source_ref=SourceRef(kind="retrieved_doc", locator="pilot-123#p4"),
                confidence=0.7,
            )],
            reasoning="model rationale here",
            scored_by="llm",
        )
        for k in DIMENSION_KEYS
    ]


def test_llm_contract_flows_through_consolidation_unchanged():
    dims, verdict, stage = consolidate(_llm_results(), stage="DI1")
    assert {d.scored_by for d in dims} == {"llm"}                  # provenance preserved
    src = dims[0].evidence_detail[0].source_ref
    assert src.kind == "retrieved_doc" and src.locator == "pilot-123#p4"
    assert verdict.composite is not None                           # engine still runs, unchanged


def test_agent_context_is_minimal_and_frozen():
    ctx = AgentContext(submission=STRONG)
    assert ctx.submission is STRONG
    with pytest.raises(Exception):
        ctx.submission = STRONG            # frozen dataclass


# ── Determinism: behaviour is unchanged ───────────────────────────────────

def _projection(a):
    """Scoring-relevant projection (excludes the assessed_at timestamp)."""
    return {
        "composite": a.verdict.composite,
        "gate": a.verdict.gate_decision.value,
        "stage": a.verdict.assigned_stage.value if a.verdict.assigned_stage else None,
        "hitl": a.verdict.requires_human_review,
        "dims": [
            (d.dimension, d.value, d.confidence, tuple(d.evidence), tuple(d.gaps), d.scored_by)
            for d in a.dimensions
        ],
    }


def test_assessment_is_deterministic_and_rubric_scored():
    a1 = asyncio.run(assess_submission(STRONG))
    a2 = asyncio.run(assess_submission(STRONG))
    assert _projection(a1) == _projection(a2)                # identical across runs
    assert {d.scored_by for d in a1.dimensions} == {"rubric"}
    for d in a1.dimensions:
        assert all(isinstance(x, str) for x in d.evidence)   # legacy shape intact
        assert all(isinstance(x, Evidence) for x in d.evidence_detail)
