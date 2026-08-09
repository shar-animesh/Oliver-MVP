"""
Pydantic models — aligned with the Canonical Scoring Service (document 04).

Uses the 0–100 / 5-dimension model with stage-adaptive weights (weight-set/3.1.0),
the completeness pre-gate, the ≥70 gate threshold, and confidence-based HITL routing.
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, computed_field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums (matching CSS domain constants) ────────────────────────────────

class DIStage(str, Enum):
    DI1 = "DI1"
    DI2 = "DI2"
    DI3 = "DI3"
    DI4 = "DI4"
    DI5 = "DI5"


class GateDecision(str, Enum):
    """The three possible gate outcomes from the canonical scoring engine."""
    GATE_PASS = "GATE_PASS"
    NO_GO_RECOMMENDED = "NO_GO_RECOMMENDED"
    COACHING_REJECT = "COACHING_REJECT"


class LifecycleState(str, Enum):
    SENSED = "Sensed"
    SUBMITTED = "Submitted"
    ASSESSING = "Assessing"
    ASSESSED = "Assessed"
    ACTIVE = "Active"
    STALLED = "Stalled"
    STELLAR = "Stellar"
    RETIRED = "Retired"


# ── Submission (input) ───────────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    """
    Mirrors what arrives via email.  Title + problem statement are the
    only truly required fields — everything else is extracted or inferred
    by the agents.
    """
    model_config = {"extra": "forbid"}

    title: str = Field(..., min_length=3, max_length=200)
    problem_statement: str = Field(..., min_length=10)
    description: str = ""
    proposed_approach: str = ""
    expected_value: str = ""
    data_sources: str = ""
    sponsor: str = ""
    team_size: Optional[int] = None
    current_stage: DIStage = DIStage.DI1   # the DI gate being assessed; defaults to DI1 for new ideas


# ── Per-agent / per-dimension results ────────────────────────────────────

class SourceRef(BaseModel):
    """
    Where a piece of evidence is grounded. Typed so the grounding can evolve
    without changing agents or consumers:
      - kind="field"          → a submission field (locator = field/check id)   [today]
      - kind="submission_span"→ an offset span in the submission text           [today/next]
      - kind="retrieved_doc"  → a RAG-retrieved document (locator = doc id+span) [future]
    Adding a new source kind is a Literal extension here — no agent code changes.
    """
    kind: Literal["field", "submission_span", "retrieved_doc"] = "field"
    locator: str = ""                                 # field name / check id / doc-id+span


class Evidence(BaseModel):
    """
    One typed, source-referenceable evidence item. This is what an agent asserts
    and what grounds a dimension score. Deterministic rubric agents populate it
    from detected submission content; LLM/RAG agents populate `source_ref` with a
    span or retrieved-doc id — same contract, richer grounding.
    """
    claim: str
    source_ref: SourceRef = Field(default_factory=SourceRef)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ── Per-agent / per-dimension results ────────────────────────────────────

class DimensionScore(BaseModel):
    """
    One dimension score from one owning agent (the persisted, consolidated form).
    Maps to the CSS SubScore: value (0–100), confidence (0–1), evidence references.

    Evidence is stored typed in `evidence_detail`; `evidence` is a computed,
    read-only projection to the legacy `list[str]` shape so every existing
    consumer (report, narrator, frontend) keeps working with no change. New code
    reads `evidence_detail`; governance/explainability persist the typed form.
    """
    agent: str                                        # owning agent name
    dimension: str                                    # canonical camelCase key
    dimension_label: str                              # human-readable label
    value: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    weight: int = Field(..., ge=0, le=100)            # weight applied for this stage
    summary: str
    evidence_detail: list[Evidence] = []              # typed evidence (source of truth)
    gaps: list[str] = []
    scored_by: str = "rubric"                         # provenance: rubric | llm | llm-fallback

    @model_validator(mode="before")
    @classmethod
    def _rehydrate_legacy_evidence(cls, data):
        """Back-compat: accept a legacy `evidence: list[str]` (old records / old
        callers) and rebuild typed Evidence when `evidence_detail` is absent.
        The legacy key is then dropped, since `evidence` is now computed."""
        if isinstance(data, dict):
            legacy = data.get("evidence")
            if legacy and not data.get("evidence_detail") and isinstance(legacy[0], str):
                data["evidence_detail"] = [
                    {"claim": s, "source_ref": {"kind": "field", "locator": "legacy"}}
                    for s in legacy
                ]
            data.pop("evidence", None)                # computed field owns this name now
        return data

    @computed_field                                   # serialized as list[str] on the wire
    @property
    def evidence(self) -> list[str]:
        return [e.claim for e in self.evidence_detail]


class AgentResult(BaseModel):
    """
    One agent's output BEFORE stage weighting — the SubScore contract.

    This is the contract a real Foundry/LLM agent emits and a Durable activity
    returns; consolidation applies the stage weight and produces a DimensionScore.
    Evidence is typed (`list[Evidence]`); `reasoning` carries an optional trace
    (a short rubric explanation today, the model's rationale under an LLM agent);
    `scored_by` records provenance. The shape is deliberately sufficient for LLM,
    RAG and tool-using agents so wiring them needs no contract change.
    """
    agent: str
    dimension: str
    dimension_label: str
    value: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = ""
    evidence: list[Evidence] = []
    gaps: list[str] = []
    reasoning: str = ""
    scored_by: str = "rubric"                         # rubric | llm | llm-fallback


# ── Verdict (canonical scoring engine output) ────────────────────────────

class VerdictResult(BaseModel):
    """
    Output of the canonical scoring engine.
    Matches CSS Result + weight-set/model references.
    """
    composite: Optional[int] = None                   # None when COACHING_REJECT
    gate_decision: GateDecision
    assigned_stage: Optional[DIStage] = None
    composite_confidence: Optional[float] = None
    lowest_confidence_dimension: Optional[str] = None
    requires_human_review: bool = False
    consistency_flags: list[str] = []
    model_version: str = "scoring-model/3.1.0"
    weight_set_version: str = "weight-set/3.1.0"


class StageAssignment(BaseModel):
    assigned_stage: DIStage
    lifecycle_state: LifecycleState
    rationale: str


class CoachingNote(BaseModel):
    message: str
    actions: list[str] = []
    next_gate_hint: str = ""


# ── Full assessment record ───────────────────────────────────────────────


class ApproachGuidance(BaseModel):
    """AI-technique coaching in plain language (the 'AI Approach Guidance' section)."""
    problem_type: str = ""
    recommended_approach: str = ""
    what_to_do_first: str = ""


class PathToNextGate(BaseModel):
    target_stage: str = ""
    target_timeline: str = ""
    milestones: list[str] = []


class TimelineGuidance(BaseModel):
    pace_note: str = ""
    risk_to_avoid: str = ""
    acceleration_move: str = ""
    suggested_next_gate: str = ""


class AssessmentNarrative(BaseModel):
    """
    The narrated assessment — the submitter-facing intelligence layer.
    Generated AFTER consolidation, grounded ONLY in the record + submission text
    (Herald guard: faithful to agent content, never invent results).
    """
    executive_summary: str = ""
    whats_working_well: list[str] = []
    coaching_message: str = ""
    coaching_recommendations: list[str] = []
    approach_guidance: ApproachGuidance = ApproachGuidance()
    path_to_next_gate: PathToNextGate = PathToNextGate()
    timeline_guidance: TimelineGuidance = TimelineGuidance()
    dimension_commentary: dict[str, str] = {}
    recommended_next_steps: list[str] = []
    closing_note: str = ""
    # Traceability register: section -> the observed evidence (quotes / stated facts)
    # that section is grounded in. Populated by the narrator.
    evidence_basis: dict[str, list[str]] = {}
    generated_by: str = "template"          # template | llm | llm-fallback


class AssessmentProvenance(BaseModel):
    """
    Run-level provenance for an LLM-scored assessment. Additive and optional so
    it does not change AgentResult, Evidence, or the deterministic path.

    Captures WHICH model produced the scoring and under WHICH prompt version,
    vendor-neutrally: `provider`/`model` come from the LLMProvider port, never
    from a concrete vendor. Per-dimension provenance (rubric | llm | llm-fallback)
    lives on DimensionScore.scored_by; the narrator records its own via
    AssessmentNarrative.generated_by.
    """
    provider: str                                     # LLMProvider.name (vendor-neutral)
    model: str                                        # configured model / deployment id
    prompt_version: str                               # e.g. "assess-prompt/1.0.0"


class Assessment(BaseModel):
    dimensions: list[DimensionScore]                  # 5 canonical dimensions
    verdict: VerdictResult
    stage: StageAssignment
    coaching: CoachingNote

    # ── Summary-report fields (the human-facing narrative) ──
    # Rendered at the top of the assessment page and in the downloadable report.
    # Derived from the same scoring pass, so the summary and detail never diverge.
    executive_summary: str = ""
    strengths: list[str] = []
    next_actions: list[str] = []
    rating: str = ""                                  # band label over the composite
    narrative: Optional[AssessmentNarrative] = None   # narrated sections (additive)
    position: str = ""                                # short "where you are" banner line
    provenance: Optional[AssessmentProvenance] = None # set when LLM evaluators scored the run

    assessed_at: datetime = Field(default_factory=_utcnow)


# ── Submission record (stored) ──────────────────────────────────────────

class Submission(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)
    state: LifecycleState = LifecycleState.SUBMITTED
    input: SubmissionCreate
    assessment: Optional[Assessment] = None

    # ── Provenance / ingestion ──
    # source: where the submission entered — "web" (dashboard test harness) or
    # "email" (ingested via Power Automate → HTTP Function).
    # source_message_id: the inbound email's internet message-id — the idempotency
    # key for the ingest path, stored on the record so dedup survives restarts.
    source: str = "web"
    source_message_id: Optional[str] = None
    stage_entered_at: datetime = Field(default_factory=_utcnow)  # when it entered its current stage (Pacer)
