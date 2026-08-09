"""
Prompt architecture for LLM evaluators.

Prompts are built DIRECTLY from the deterministic rubric — the same weighted
criteria the deterministic evaluators score — not from new evaluation logic. Each
dimension's criteria are transcribed here as declarative data (id, description,
weight) mirroring the checks in mock_assessor, and rendered into vendor-neutral
`Message`s. The model is asked to return a strict JSON object that maps 1:1 into
`AgentResult` (validated downstream before it enters the system).

`PROMPT_VERSION` is surfaced in provenance so a score is always attributable to a
prompt revision. Bump it on any change to the criteria or the instructions.
"""
from __future__ import annotations

from dataclasses import dataclass

from oliver_core.providers.base import Message
from oliver_core.schemas import SubmissionCreate

PROMPT_VERSION = "assess-prompt/1.0.0"


@dataclass(frozen=True)
class Criterion:
    id: str
    description: str
    weight: int


@dataclass(frozen=True)
class DimensionRubric:
    agent: str
    dimension: str
    label: str
    criteria: tuple[Criterion, ...]


# ── Rubric, transcribed from the deterministic checks (weights sum to 100) ──
DIMENSION_RUBRICS: dict[str, DimensionRubric] = {
    "ideaCompleteness": DimensionRubric(
        "DocGuard", "ideaCompleteness", "Idea Completeness",
        (
            Criterion("problem_present", "A problem or need is stated at all", 15),
            Criterion("problem_substantive", "The problem is substantive, not a one-liner", 15),
            Criterion("problem_detailed", "The problem has concrete detail (who/how often/impact)", 10),
            Criterion("approach_provided", "A proposed approach or solution is present", 12),
            Criterion("approach_substantive", "The approach is more than a slogan", 8),
            Criterion("value_stated", "An expected value or benefit is stated", 12),
            Criterion("data_sources_named", "The data the idea would use is named", 10),
            Criterion("sponsor_named", "A sponsor or accountable owner is referenced", 8),
            Criterion("team_specified", "Who would run it is indicated", 5),
            Criterion("context_provided", "Supporting context is provided", 5),
        ),
    ),
    "ideaQuality": DimensionRubric(
        "IdeaPulse", "ideaQuality", "Idea Quality",
        (
            Criterion("problem_specific", "The problem is specific, not generic", 15),
            Criterion("impact_quantified", "The impact is quantified (a number, %, or figure)", 20),
            Criterion("consequence_stated", "The consequence of inaction is stated", 15),
            Criterion("stakeholders_clear", "Affected stakeholders are clear", 10),
            Criterion("approach_concrete", "The approach is concrete", 15),
            Criterion("problem_approach_fit", "The approach fits the stated problem", 10),
            Criterion("depth_of_detail", "There is genuine depth of detail", 15),
        ),
    ),
    "strategicValue": DimensionRubric(
        "ValuePulse", "strategicValue", "Strategic / Business Value",
        (
            Criterion("value_explicit", "The business value is stated explicitly", 20),
            Criterion("financial_quantified", "At least one benefit is financially quantified", 20),
            Criterion("efficiency_claimed", "A concrete efficiency gain is described", 15),
            Criterion("scale_indicated", "The scale of impact is indicated", 15),
            Criterion("value_substantive", "The value claim is substantive, not aspirational", 15),
            Criterion("baseline_referenced", "Today's baseline is referenced for comparison", 15),
        ),
    ),
    "technicalFeasibility": DimensionRubric(
        "TechScope", "technicalFeasibility", "Technical Feasibility",
        (
            Criterion("approach_specified", "A technical approach is specified", 20),
            Criterion("approach_detailed", "The approach has enough technical detail", 15),
            Criterion("data_sources_named", "Concrete data sources are named", 20),
            Criterion("data_substantive", "The data description is substantive", 15),
            Criterion("integration_surface", "Integration/deployment surface is noted", 15),
            Criterion("context_supports_tech", "Context supports technical feasibility", 15),
        ),
    ),
    "executionReadiness": DimensionRubric(
        "PathFinder", "executionReadiness", "Execution Readiness",
        (
            Criterion("sponsor_identified", "A sponsor or accountable owner is identified", 25),
            Criterion("sponsor_substantive", "The sponsor reference is substantive", 10),
            Criterion("team_adequate", "The team/capacity is adequate for the work", 20),
            Criterion("team_present", "A team is at least present", 10),
            Criterion("scope_manageable", "The scope is manageable for a pilot", 15),
            Criterion("execution_context", "Execution context (milestone/plan) is present", 20),
        ),
    ),
}

_SYSTEM_TEMPLATE = (
    "You are {agent}, an evaluator in the Oliver AI-pilot stage-gate. Score the "
    "'{label}' dimension of a submission from 0 to 100 using ONLY the weighted "
    "criteria provided. Rules:\n"
    "- Evidence-mandatory: justify credit with a short verbatim quote from the "
    "submission. If something is missing, record it as a gap — never invent it.\n"
    "- The score must reflect the weighted criteria (max points shown per "
    "criterion; they total 100).\n"
    "- 'confidence' (0.0-1.0) reflects how much explicit evidence you found.\n"
    "Return ONLY a single JSON object, no prose, with exactly these keys:\n"
    '{{"value": <int 0-100>, "confidence": <float 0-1>, "summary": "<one sentence>", '
    '"evidence": [{{"claim": "<why credit was given>", "excerpt": "<verbatim quote>", '
    '"confidence": <float 0-1>}}], "gaps": ["<what is missing>"], '
    '"reasoning": "<brief justification of the score>"}}'
)


def _submission_block(sub: SubmissionCreate) -> str:
    fields = {
        "title": sub.title,
        "problem_statement": sub.problem_statement,
        "proposed_approach": sub.proposed_approach,
        "expected_value": sub.expected_value,
        "data_sources": sub.data_sources,
        "sponsor": sub.sponsor,
        "team_size": sub.team_size,
        "description": sub.description,
    }
    lines = [f"- {k}: {v}" for k, v in fields.items() if v not in (None, "")]
    return "\n".join(lines) if lines else "- (no fields provided)"


def build_messages(dimension: str, sub: SubmissionCreate) -> list[Message]:
    """Render the rubric for `dimension` and the submission into chat messages."""
    rubric = DIMENSION_RUBRICS[dimension]
    system = _SYSTEM_TEMPLATE.format(agent=rubric.agent, label=rubric.label)
    criteria = "\n".join(
        f"- [{c.id}] {c.description} (max {c.weight} pts)" for c in rubric.criteria
    )
    user = (
        f"Weighted criteria for '{rubric.label}':\n{criteria}\n\n"
        f"Submission:\n{_submission_block(sub)}"
    )
    return [Message(role="system", content=system), Message(role="user", content=user)]
