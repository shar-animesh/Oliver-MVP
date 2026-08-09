"""
Ingestion layer — host-agnostic.

Turns an inbound email (as Power Automate will POST it) into a stored, assessed
record. Deliberately separated from assessment: this module orchestrates
idempotency → normalization → persistence and *delegates* scoring to
`assess_submission`. It never reimplements the pipeline.

Two thin hosts call `ingest_email`:
  • the FastAPI endpoint  `POST /api/v1/ingest/email`   (live + testable today)
  • the Azure Function    `services/ingest-func/function_app.py`  (deployment target)

Because both call the same function, moving from local to Azure — and pointing
Power Automate at it — is a deployment/config concern, not a code rewrite.
"""

from __future__ import annotations

import html as _html
import re
from datetime import datetime
from typing import Awaitable, Callable, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from oliver_core import store, audit
from oliver_core.mock_assessor import assess_submission
from oliver_core.schemas import (
    Assessment, LifecycleState, Submission, SubmissionCreate,
)


# ── Boundary contracts ───────────────────────────────────────────────────

class InboundEmail(BaseModel):
    """The normalized payload Power Automate posts for each received email."""
    message_id: str = Field(..., min_length=1)   # internet message-id — idempotency key
    subject: str = ""
    body: str = ""                                # plain-text body
    from_address: str = ""
    received_at: Optional[datetime] = None
    attachments: list[str] = []                   # names only (informational)


class IngestResult(BaseModel):
    submission_id: UUID
    status: str            # "created" | "duplicate"
    message_id: str
    # The rendered submitter-facing assessment email (Phase-A delivery: Power
    # Automate replies to the sender with this HTML). Populated ONLY on
    # status="created" — duplicates get none, so a re-fired flow cannot
    # double-email the submitter.
    report_html: Optional[str] = None


# ── Email → submission normalization ─────────────────────────────────────
#
# The scorer tolerates prose, but *dirty* prose (signatures, quoted history)
# still corrupts inference — so we clean before handing off. Kept conservative:
# better to under-strip than to delete real content.

_RE_SUBJECT_PREFIX = re.compile(r"^\s*(re|fwd?|fw)\s*:\s*", re.IGNORECASE)

# First reply-chain marker: cut everything from here down.
_RE_QUOTE_MARKER = re.compile(
    r"^\s*(-{2,}\s*original message\s*-{2,}"
    r"|On .+ wrote:\s*$"
    r"|From:\s.+"
    r"|_{5,})",
    re.IGNORECASE | re.MULTILINE,
)
_RE_SIG_DELIM = re.compile(r"\n-- \n")                      # standard signature delimiter
_RE_SENT_FROM = re.compile(r"^\s*sent from my .*$", re.IGNORECASE | re.MULTILINE)



# ── HTML sanitization ─────────────────────────────────────────────────────
# Outlook/Graph deliver HTML bodies. Never trust the flow to convert: strip
# markup server-side so the stored problem_statement is always clean prose.
_RE_HTML_HINT = re.compile(r"<\s*(?:html|head|body|div|p|br|span|meta|style|table)\b", re.IGNORECASE)
_RE_BLOCKS = re.compile(r"<(style|script|head)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_RE_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_BREAKS = re.compile(r"<\s*(?:br\s*/?|/p|/div|/tr|/li)\s*>", re.IGNORECASE)
_RE_TAGS = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """If the body looks like HTML, reduce it to clean plain text."""
    if not _RE_HTML_HINT.search(text):
        return text
    t = _RE_BLOCKS.sub(" ", text)
    t = _RE_COMMENTS.sub(" ", t)
    t = _RE_BREAKS.sub("\n", t)
    t = _RE_TAGS.sub(" ", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def _clean_subject(subject: str) -> str:
    s = (subject or "").strip()
    prev = None
    while prev != s:                                        # strip repeated Re:/Fwd:
        prev = s
        s = _RE_SUBJECT_PREFIX.sub("", s).strip()
    return s.strip()


def _clean_body(body: str) -> str:
    text = _strip_html((body or "").replace("\r\n", "\n"))
    m = _RE_QUOTE_MARKER.search(text)                       # cut quoted history
    if m:
        text = text[: m.start()]
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith(">"))
    text = _RE_SIG_DELIM.split(text, 1)[0]                  # cut signature block
    text = _RE_SENT_FROM.sub("", text)                      # drop mobile-sig lines
    return text.strip()


def normalize(email: InboundEmail) -> SubmissionCreate:
    """Map a cleaned email onto the submission contract. Raises if there's no content."""
    title = _clean_subject(email.subject)
    if len(title) < 3:
        title = "(no subject)"
    problem = _clean_body(email.body)
    if len(problem) < 10:
        raise ValueError("Email body has no assessable content after cleaning.")
    return SubmissionCreate(title=title[:200], problem_statement=problem)


# ── Idempotency ──────────────────────────────────────────────────────────
#
# Keyed on the internet message-id, stored on the record, so dedup survives a
# restart. MVP lookup scans list_all() — fine at pilot volume. Production note:
# a durable store should point-query message-id (a Cosmos WHERE / unique key) and
# enforce it atomically to close the concurrent-delivery race. See delivery log.

def find_by_message_id(store_module, message_id: str) -> Optional[Submission]:
    for sub in store_module.list_all():
        if sub.source_message_id == message_id:
            return sub
    return None


# ── Orchestration ────────────────────────────────────────────────────────

AssessFn = Callable[[SubmissionCreate], Awaitable[Assessment]]


async def ingest_email(
    email: InboundEmail,
    *,
    actor: str = "system",
    assess_fn: AssessFn = assess_submission,
    store_module=store,
) -> IngestResult:
    """
    Idempotent ingestion:
      1. if this message-id was already ingested → return the existing record (no re-assess)
      2. normalize the email → SubmissionCreate
      3. persist a SUBMITTED/ASSESSING record (exists immediately — models the async window)
      4. delegate scoring to assess_fn (the pipeline, unchanged), persist the ASSESSED record

    assess_fn is injectable so a future step can swap synchronous scoring for
    "enqueue to a Durable orchestrator" without touching ingestion.
    """
    existing = find_by_message_id(store_module, email.message_id)
    if existing is not None:
        return IngestResult(
            submission_id=existing.id, status="duplicate", message_id=email.message_id
        )

    sub_input = normalize(email)                            # may raise ValueError
    submission = Submission(
        input=sub_input,
        source="email",
        source_message_id=email.message_id,
        state=LifecycleState.ASSESSING,
    )
    store_module.put(submission)                            # record visible before scoring
    audit.record_submission_received(submission, actor=actor)

    submission.assessment = await assess_fn(sub_input)
    submission.state = submission.assessment.stage.lifecycle_state
    store_module.put(submission)
    audit.record_assessment(submission, actor=actor)

    # Render the submitter-facing report for Phase-A delivery (PA replies with it).
    from oliver_core.email_report import render_submitter_email
    report_html = render_submitter_email(submission)
    audit.record("report_rendered", subject=str(submission.id),
                 payload={"bytes": len(report_html), "channel": "ingest-response"})

    return IngestResult(
        submission_id=submission.id, status="created", message_id=email.message_id,
        report_html=report_html,
    )
