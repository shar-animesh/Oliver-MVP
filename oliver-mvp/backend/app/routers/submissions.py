"""Submission endpoints."""

from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from app.auth import current_actor, require_writer

from oliver_core.schemas import (
    LifecycleState, Submission, SubmissionCreate,
)
from oliver_core import mock_assessor as assessor, store, audit
from oliver_core.report import render_report_html
from oliver_core import herald, pacer

router = APIRouter(tags=["submissions"])


@router.post("/submissions", response_model=Submission, status_code=201)
async def create_submission(body: SubmissionCreate, actor: str = Depends(require_writer)):
    sub = Submission(input=body)
    store.put(sub)
    audit.record_submission_received(sub, actor=actor)
    return sub


@router.get("/submissions", response_model=list[Submission])
async def list_submissions():
    return store.list_all()


@router.get("/submissions/{submission_id}", response_model=Submission)
async def get_submission(submission_id: UUID):
    sub = store.get(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    return sub


@router.post("/test-assess", response_model=Submission)
async def test_assess(body: SubmissionCreate, actor: str = Depends(require_writer)):
    """Door-B synchronous harness: create + assess in one call (admin / testing)."""
    sub = Submission(input=body, source="web")
    audit.record_submission_received(sub, actor=actor)
    sub.assessment = await assessor.assess_submission(sub.input)
    sub.state = sub.assessment.stage.lifecycle_state
    store.put(sub)
    audit.record_assessment(sub, actor=actor)
    return sub


@router.post("/submissions/{submission_id}/deliver")
async def deliver(submission_id: UUID, to: str | None = None, actor: str = Depends(require_writer)):
    """Door-B: render + persist + deliver the assessment report (Graph adapter at deployment)."""
    sub = store.get(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    if not sub.assessment:
        raise HTTPException(409, "Submission has not been assessed yet")
    return herald.deliver_assessment(sub, recipient=to, actor=actor)


@router.get("/submissions/{submission_id}/cadence")
async def cadence(submission_id: UUID):
    sub = store.get(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    return pacer.cadence_for(sub.input.current_stage.value, sub.stage_entered_at)


@router.post("/submissions/{submission_id}/advance")
async def advance(submission_id: UUID, actor: str = Depends(require_writer)):
    sub = store.get(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    if not sub.assessment:
        raise HTTPException(409, "Submission has not been assessed yet")
    advanced = pacer.advance_on_pass(sub, actor=actor)
    if advanced:
        store.put(sub)
    return {"advanced": advanced, "current_stage": sub.input.current_stage.value}


@router.get("/pacer/stalled")
async def stalled():
    out = []
    for s in store.list_all():
        cad = pacer.cadence_for(s.input.current_stage.value, s.stage_entered_at)
        if cad.stalled:
            out.append({"id": str(s.id), "stage": cad.stage, "days_in_stage": cad.days_in_stage})
    return out


@router.get("/submissions/{submission_id}/report/email")
async def submitter_email_report(submission_id: UUID):
    """
    The submitter-facing assessment email (historical Oliver format), rendered
    from the stored record. Used for browser preview and as an alternative
    Phase-A fetch for Power Automate.
    """
    sub = store.get(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    if not sub.assessment:
        raise HTTPException(409, "Submission has not been assessed yet")
    from oliver_core.email_report import render_submitter_email
    return Response(content=render_submitter_email(sub), media_type="text/html")


@router.get("/submissions/{submission_id}/report")
async def download_report(submission_id: UUID):
    """
    Render the complete structured assessment report as a downloadable HTML file.
    Generated from the stored assessment record — the same source as the on-page summary.
    """
    sub = store.get(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")
    if not sub.assessment:
        raise HTTPException(409, "Submission has not been assessed yet")

    html_doc = render_report_html(sub)
    short = str(sub.id)[:8]
    return Response(
        content=html_doc,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="Oliver-Assessment-{short}.html"'
        },
    )


@router.post("/assess/{submission_id}", response_model=Submission)
async def assess(submission_id: UUID, actor: str = Depends(require_writer)):
    """Trigger the mock assessment pipeline for a submission."""
    sub = store.get(submission_id)
    if not sub:
        raise HTTPException(404, "Submission not found")

    sub.state = LifecycleState.ASSESSING
    # ── This is the line you replace with real agent calls ──
    sub.assessment = await assessor.assess_submission(sub.input)
    # ─────────────────────────────────────────────────────────
    sub.state = sub.assessment.stage.lifecycle_state
    store.put(sub)
    audit.record_assessment(sub, actor=actor)
    return sub
