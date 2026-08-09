"""
Oliver MVP — scoring tests.

Validates that the rubric-based mock evaluators produce differentiated,
explainable scores, and that the canonical scoring engine produces
correct gate decisions.
"""

import asyncio
import pytest
from oliver_core.schemas import SubmissionCreate
from oliver_core.mock_assessor import (
    assess_submission, score_composite, run_scoring_engine,
    WEIGHTS_BY_STAGE, DIMENSION_KEYS, GATE_THRESHOLD, COMPLETENESS_FLOOR,
)


# ── Test fixtures ────────────────────────────────────────────────────────

THIN_FRIVOLOUS = SubmissionCreate(
    title="AI Coffee Recommendation Bot",
    problem_statement="Employees waste time deciding what coffee to order.",
)

THIN_SERIOUS = SubmissionCreate(
    title="Predictive Maintenance for Gas Turbines",
    problem_statement="Unplanned downtime on gas turbine fleet costs 2M EUR per year.",
)

MEDIUM = SubmissionCreate(
    title="Contract Review Assistant",
    problem_statement="Manual review of procurement contracts takes 3 weeks per batch. Legal team is overloaded.",
    proposed_approach="Use NLP to flag non-standard clauses and extract key terms from contract PDFs.",
    expected_value="50% reduction in review time, saving approximately 200K EUR annually.",
)

RICH = SubmissionCreate(
    title="Predictive Maintenance for Gas Turbines",
    problem_statement="Unplanned downtime on our gas turbine fleet costs approximately 2M EUR per year. "
                      "We need 48-hour advance warning of failures to schedule maintenance windows.",
    proposed_approach="Time-series anomaly detection on vibration sensor data using LSTM networks. "
                      "The model will ingest streaming data from PI System and flag anomalous patterns.",
    expected_value="30% reduction in unplanned outages, estimated 600K EUR per year in savings. "
                   "Secondary benefit: optimized spare parts inventory.",
    data_sources="PI System historian (vibration, temperature, pressure), SAP PM work order history",
    sponsor="VP Gas Services",
    team_size=4,
    description="Building on a successful 3-month proof of concept with the Kassel fleet. "
                "The PoC demonstrated 85% anomaly detection accuracy on historical data.",
)

ULTRA_THIN = SubmissionCreate(
    title="Something AI",
    problem_statement="We should do something with AI.",
)


# Same strong idea in three formats — for prose-inference tests
STRUCTURED = SubmissionCreate(
    title="Predictive Maintenance for Gas Turbines",
    problem_statement="Unplanned downtime on our gas turbine fleet costs approximately 2M EUR per year. We need 48-hour advance warning.",
    proposed_approach="Time-series anomaly detection on vibration sensor data using LSTM networks.",
    expected_value="30% reduction in unplanned outages, ~600K EUR per year in savings.",
    data_sources="PI System historian (vibration, temperature, pressure)",
    sponsor="VP Gas Services",
    team_size=4,
)

EMAIL_PROSE = SubmissionCreate(
    title="Predictive Maintenance for Gas Turbines",
    problem_statement=(
        "Hi, I'm writing on behalf of our VP of Gas Services. Our turbine fleet "
        "loses about 2M EUR a year to unplanned downtime, and I think we could "
        "predict failures 48 hours ahead using anomaly detection on the vibration "
        "data we already collect in PI System. I've got a team of four ready to "
        "prototype this next quarter, and we expect to cut outages by 30%."
    ),
)


# ── Score differentiation tests ──────────────────────────────────────────

class TestScoreDifferentiation:
    """The core requirement: different-quality submissions must produce
    meaningfully different scores."""

    def _assess(self, sub):
        return asyncio.run(assess_submission(sub))

    def test_rich_scores_higher_than_thin(self):
        thin = self._assess(THIN_FRIVOLOUS)
        rich = self._assess(RICH)
        # Thin may be COACHING_REJECT (composite=None), which is effectively 0
        thin_score = thin.verdict.composite if thin.verdict.composite is not None else 0
        assert rich.verdict.composite > thin_score + 25, (
            f"Rich ({rich.verdict.composite}) should exceed thin ({thin_score}) by >25 points"
        )

    def test_medium_scores_between_thin_and_rich(self):
        thin = self._assess(THIN_FRIVOLOUS)
        med = self._assess(MEDIUM)
        rich = self._assess(RICH)
        thin_score = thin.verdict.composite if thin.verdict.composite is not None else 0
        assert thin_score < med.verdict.composite < rich.verdict.composite, (
            f"Expected thin ({thin_score}) < medium ({med.verdict.composite}) "
            f"< rich ({rich.verdict.composite})"
        )

    def test_spread_exceeds_25_points(self):
        thin = self._assess(THIN_FRIVOLOUS)
        rich = self._assess(RICH)
        thin_score = thin.verdict.composite if thin.verdict.composite is not None else 0
        spread = rich.verdict.composite - thin_score
        assert spread > 25, f"Score spread {spread} is too narrow (need >25)"

    def test_rich_submission_passes_gate(self):
        result = self._assess(RICH)
        assert result.verdict.gate_decision.value == "GATE_PASS", (
            f"Rich submission should pass gate, got {result.verdict.gate_decision.value} "
            f"with composite {result.verdict.composite}"
        )

    def test_thin_submission_does_not_pass_gate(self):
        result = self._assess(THIN_FRIVOLOUS)
        assert result.verdict.gate_decision.value != "GATE_PASS", (
            f"Thin submission should not pass gate, got composite {result.verdict.composite}"
        )


# ── Evidence traceability tests ──────────────────────────────────────────

class TestEvidenceTraceability:
    """Every evidence statement must be traceable to submission content."""

    def _assess(self, sub):
        return asyncio.run(assess_submission(sub))

    def test_no_false_evidence_claims(self):
        """A thin submission should not claim evidence that isn't there."""
        result = self._assess(THIN_FRIVOLOUS)
        for dim in result.dimensions:
            for ev in dim.evidence:
                # Evidence for passed checks should not claim presence of absent fields
                assert "not provided" not in ev, (
                    f"Evidence list contains a negative claim: '{ev}' — "
                    f"negatives belong in gaps, not evidence"
                )

    def test_gaps_cite_what_is_missing(self):
        """Gaps should explain what's missing."""
        result = self._assess(THIN_FRIVOLOUS)
        total_gaps = sum(len(d.gaps) for d in result.dimensions)
        assert total_gaps >= 10, (
            f"Thin submission should have many gaps, found only {total_gaps}"
        )

    def test_rich_has_more_evidence_than_gaps(self):
        result = self._assess(RICH)
        total_ev = sum(len(d.evidence) for d in result.dimensions)
        total_gaps = sum(len(d.gaps) for d in result.dimensions)
        assert total_ev > total_gaps, (
            f"Rich submission should have more evidence ({total_ev}) than gaps ({total_gaps})"
        )

    def test_evidence_contains_submission_content(self):
        """Evidence for rich submission should cite actual field values."""
        result = self._assess(RICH)
        all_evidence = " ".join(ev for d in result.dimensions for ev in d.evidence)
        assert "VP Gas Services" in all_evidence, "Should cite actual sponsor name"
        # The quantity regex finds "30%" or "600K EUR" or "2M EUR" — check any quantified claim is cited
        assert any(term in all_evidence for term in ["30%", "600K", "2M"]), (
            "Should cite at least one quantified financial figure from submission"
        )


# ── Canonical engine tests ───────────────────────────────────────────────

class TestCanonicalEngine:
    """The scoring engine must be correct regardless of mock agent changes."""

    def test_weight_sets_sum_to_100(self):
        for stage, w in WEIGHTS_BY_STAGE.items():
            assert sum(w.values()) == 100, f"{stage} weights sum to {sum(w.values())}"

    def test_gate_pass_at_70(self):
        scores = {k: 70 for k in DIMENSION_KEYS}
        confs = {k: 0.9 for k in DIMENSION_KEYS}
        result = run_scoring_engine(scores, confs, "DI1")
        assert result["composite"] == 70
        assert result["gate_decision"].value == "GATE_PASS"

    def test_no_go_at_69(self):
        scores = {k: 69 for k in DIMENSION_KEYS}
        confs = {k: 0.9 for k in DIMENSION_KEYS}
        result = run_scoring_engine(scores, confs, "DI1")
        assert result["composite"] == 69
        assert result["gate_decision"].value == "NO_GO_RECOMMENDED"

    def test_coaching_reject_below_floor(self):
        scores = {k: 70 for k in DIMENSION_KEYS}
        scores["ideaCompleteness"] = 29
        confs = {k: 0.9 for k in DIMENSION_KEYS}
        result = run_scoring_engine(scores, confs, "DI1")
        assert result["gate_decision"].value == "COACHING_REJECT"
        assert result["composite"] is None

    def test_hitl_on_low_confidence(self):
        scores = {k: 75 for k in DIMENSION_KEYS}
        confs = {k: 0.5 for k in DIMENSION_KEYS}  # below 0.6 floor
        result = run_scoring_engine(scores, confs, "DI1")
        assert result["gate_decision"].value == "GATE_PASS"
        assert result["requires_human_review"] is True


# ── Coaching quality tests ───────────────────────────────────────────────

class TestCoaching:
    def _assess(self, sub):
        return asyncio.run(assess_submission(sub))

    def test_coaching_reject_message(self):
        result = self._assess(ULTRA_THIN)
        assert "completeness" in result.coaching.message.lower() or "detail" in result.coaching.message.lower()

    def test_gate_pass_coaching_mentions_strengths(self):
        result = self._assess(RICH)
        if result.verdict.gate_decision.value == "GATE_PASS":
            assert "strong" in result.coaching.message.lower() or "clears" in result.coaching.message.lower()

    def test_nogo_coaching_names_weak_dimensions(self):
        result = self._assess(THIN_SERIOUS)
        if result.verdict.gate_decision.value == "NO_GO_RECOMMENDED":
            # Should name specific weak areas, not generic message
            assert len(result.coaching.actions) >= 2


# ── Dimension count test ────────────────────────────────────────────────

class TestProseInference:
    """Oliver assesses email prose, not just structured forms.
    Evidence expressed in natural language must count."""

    def _assess(self, sub):
        return asyncio.run(assess_submission(sub))

    def test_email_prose_scores_close_to_structured(self):
        """Same idea, structured vs prose, should score within 15 points."""
        s = self._assess(STRUCTURED)
        e = self._assess(EMAIL_PROSE)
        assert abs(s.verdict.composite - e.verdict.composite) <= 15, (
            f"Structured ({s.verdict.composite}) and prose ({e.verdict.composite}) "
            f"differ by more than 15 points — prose inference is under-crediting"
        )

    def test_email_prose_passes_gate(self):
        """A strong idea in email form should clear the gate."""
        e = self._assess(EMAIL_PROSE)
        assert e.verdict.gate_decision.value == "GATE_PASS", (
            f"Strong email prose should pass, got {e.verdict.gate_decision.value} "
            f"(composite {e.verdict.composite})"
        )

    def test_prose_sponsor_inferred(self):
        """Sponsor mentioned in prose ('on behalf of our VP') must be detected."""
        e = self._assess(EMAIL_PROSE)
        pathfinder = next(d for d in e.dimensions if d.dimension == "executionReadiness")
        sponsor_ev = " ".join(pathfinder.evidence)
        assert "inferred from text" in sponsor_ev or "VP" in sponsor_ev, (
            "Sponsor referenced in prose was not inferred"
        )

    def test_prose_execution_inferred(self):
        """'team of four ready to prototype' must register as execution capacity."""
        e = self._assess(EMAIL_PROSE)
        pathfinder = next(d for d in e.dimensions if d.dimension == "executionReadiness")
        assert pathfinder.value >= 50, (
            f"Execution readiness only {pathfinder.value} despite team + timeline in prose"
        )

    def test_prose_data_source_inferred(self):
        """'vibration data we already collect in PI System' must register as a data source."""
        e = self._assess(EMAIL_PROSE)
        tech = next(d for d in e.dimensions if d.dimension == "technicalFeasibility")
        data_ev = " ".join(tech.evidence)
        assert "PI System" in data_ev or "inferred from text" in data_ev, (
            "Data source named in prose was not inferred"
        )

    def test_prose_evidence_still_traceable(self):
        """Inferred evidence must quote actual submission text, not invent it."""
        e = self._assess(EMAIL_PROSE)
        for d in e.dimensions:
            for ev in d.evidence:
                # Inferred evidence is marked and quotes text
                if "inferred from text" in ev:
                    assert '"' in ev, f"Inferred evidence must quote the source text: {ev}"

    def test_thin_still_rejects(self):
        """Prose inference must not rescue a genuinely empty submission."""
        t = self._assess(ULTRA_THIN)
        assert t.verdict.gate_decision.value in ("COACHING_REJECT", "NO_GO_RECOMMENDED")


class TestStructure:
    def _assess(self, sub):
        return asyncio.run(assess_submission(sub))

    def test_always_five_dimensions(self):
        for sub in [THIN_FRIVOLOUS, MEDIUM, RICH]:
            result = self._assess(sub)
            assert len(result.dimensions) == 5

    def test_all_scores_in_range(self):
        for sub in [THIN_FRIVOLOUS, MEDIUM, RICH]:
            result = self._assess(sub)
            for d in result.dimensions:
                assert 0 <= d.value <= 100, f"{d.dimension}: {d.value} out of range"
                assert 0.0 <= d.confidence <= 1.0, f"{d.dimension}: conf {d.confidence} out of range"
