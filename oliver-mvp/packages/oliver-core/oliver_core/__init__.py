"""
oliver-core — the framework-free heart of the Oliver Lifecycle Mesh.

Everything needed to turn a submission into an assessed, renderable record —
independent of *how* it is triggered (web, HTTP Function, Durable orchestrator)
or *where* records are stored. This is the shared package imported by both the
ingestion/assessment path and the dashboard read API.

Contents:
  schemas        — the record contracts (SubmissionCreate, Assessment, ...)
  mock_assessor  — the assessment pipeline + canonical scoring engine + summary
                   synthesis. (The five evaluator BODIES are the mock; the
                   engine, stage logic, and consolidation are production logic.)
  report         — the structured-report renderer (also reused by Herald)
  store          — the record store interface (in-memory today; durable next)

Import submodules explicitly, e.g. `from oliver_core.schemas import Assessment`.
The names below are re-exported for convenience.
"""

from oliver_core.schemas import (
    SubmissionCreate,
    Submission,
    Assessment,
    DimensionScore,
    AgentResult,
    Evidence,
    SourceRef,
    VerdictResult,
    StageAssignment,
    CoachingNote,
    DIStage,
    GateDecision,
    LifecycleState,
)
from oliver_core.mock_assessor import assess_submission, AgentContext
from oliver_core.report import render_report_html

__version__ = "0.1.0"

__all__ = [
    "SubmissionCreate", "Submission", "Assessment", "DimensionScore",
    "AgentResult", "Evidence", "SourceRef", "AgentContext",
    "VerdictResult", "StageAssignment", "CoachingNote",
    "DIStage", "GateDecision", "LifecycleState",
    "assess_submission", "render_report_html",
]
