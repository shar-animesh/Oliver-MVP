"""Narrative layer + submitter email report tests."""
import asyncio

from oliver_core.ingest import InboundEmail, ingest_email
from oliver_core.mock_assessor import assess_submission
from oliver_core.email_report import render_submitter_email
from oliver_core.schemas import Submission, SubmissionCreate
from oliver_core import store

RICH = SubmissionCreate(
    title="Predictive Maintenance for Gas Turbines",
    problem_statement=("Unplanned downtime on our gas turbine fleet costs approximately 2M EUR per year. "
                       "We need 48-hour advance warning of failures to schedule maintenance windows."),
    proposed_approach="Anomaly detection on vibration data from PI System using LSTM networks.",
    expected_value="30% reduction in unplanned outages, ~600K EUR/year savings.",
    data_sources="PI System historian", sponsor="VP Gas Services", team_size=4)


def _assessed(sc=RICH) -> Submission:
    sub = Submission(input=sc)
    sub.assessment = asyncio.run(assess_submission(sc))
    return sub


class TestNarrative:
    def test_all_sections_populated(self):
        a = _assessed().assessment
        n = a.narrative
        assert n is not None and n.generated_by == "template"
        assert n.executive_summary and n.whats_working_well
        assert n.approach_guidance.problem_type and n.approach_guidance.recommended_approach
        assert n.path_to_next_gate.milestones and n.path_to_next_gate.target_stage.startswith("DI2")
        assert n.timeline_guidance.risk_to_avoid and n.recommended_next_steps
        assert set(n.dimension_commentary) == {d.dimension for d in a.dimensions}

    def test_summary_references_the_proposal_not_only_scores(self):
        a = _assessed().assessment
        assert "turbine" in a.narrative.executive_summary.lower()

    def test_problem_type_inference_differs_by_domain(self):
        text_doc = SubmissionCreate(title="Proposal review assistant",
            problem_statement="Engineering teams spend long hours reviewing project proposals and documents manually before approval.")
        n1 = _assessed(RICH).assessment.narrative
        n2 = _assessed(text_doc).assessment.narrative
        assert n1.approach_guidance.problem_type != n2.approach_guidance.problem_type

    def test_no_rubric_internals_in_narrative(self):
        n = _assessed().assessment.narrative
        blob = n.model_dump_json()
        assert "threshold:" not in blob and "chars (" not in blob  # rubric-internal patterns, not the word


class TestSubmitterEmail:
    def test_sections_render(self):
        html = render_submitter_email(_assessed())
        for needle in ("Executive Summary", "What's Working Well", "Coaching Recommendations",
                       "AI Approach Guidance", "Path to", "Timeline Guidance",
                       "Assessment Score Breakdown", "Recommended Next Steps",
                       "We welcome resubmissions", "Oliver Smith"):
            assert needle in html, f"missing section: {needle}"

    def test_email_safe_and_escaped(self):
        evil = SubmissionCreate(title="<script>alert(1)</script> Idea",
            problem_statement="A submission containing <b>markup</b> that must be escaped in the report output safely.")
        html = render_submitter_email(_assessed(evil))
        assert "<script>" not in html and "&lt;script&gt;" in html

    def test_ingest_returns_report_only_on_created(self):
        store.set_backend(store.MemoryBackend())
        email = InboundEmail(message_id="nr-1", subject="Turbine idea",
            body="Unplanned turbine downtime costs us significant money and we want early failure warnings from sensor data.")
        r1 = asyncio.run(ingest_email(email))
        r2 = asyncio.run(ingest_email(email))
        assert r1.status == "created" and r1.report_html and "Executive Summary" in r1.report_html
        assert r2.status == "duplicate" and r2.report_html is None


class TestEvidenceTraceability:
    def test_no_internal_contradiction_when_approach_detected_in_prose(self):
        """The v21 defect: approach found in prose must never yield 'route undefined' coaching."""
        sc = SubmissionCreate(title="Proposal review assistant",
            problem_statement=("Engineering teams spend significant time reviewing proposals manually. "
                               "The solution uses Large Language Models integrated with Microsoft Power "
                               "Platform to analyze incoming proposals. Data sources: historical proposals."))
        n = _assessed(sc).assessment.narrative
        joined = " ".join(n.coaching_recommendations)
        assert "no technical approach can be found" not in joined.lower()
        assert "route is undefined" not in joined.lower()
        # and the commentary agrees with the coaching (both see the approach)
        assert "approach named" in n.dimension_commentary["technicalFeasibility"].lower()

    def test_inference_labels_present(self):
        n = _assessed().assessment.narrative
        blob = n.model_dump_json().lower()
        for label in ("likely", "assumed", "projected"):
            assert label in blob, f"missing inference label: {label}"

    def test_value_claim_labeled_projected(self):
        n = _assessed().assessment.narrative
        assert "projected" in n.dimension_commentary["strategicValue"].lower()

    def test_evidence_basis_populated_and_quotes_submission(self):
        n = _assessed().assessment.narrative
        assert n.evidence_basis.get("executive_summary")
        assert any("turbine" in q.lower() for q in n.evidence_basis["executive_summary"])

    def test_commentary_reads_evidence_then_analysis(self):
        n = _assessed().assessment.narrative
        assert all(c.startswith("Evidence:") and "Analysis:" in c
                   for c in n.dimension_commentary.values())

    def test_email_renders_grounding_and_legend(self):
        html = render_submitter_email(_assessed())
        assert "Grounded in:" in html and "How to read this assessment" in html
