"""Herald — host-agnostic delivery seam: persist the report, build an email envelope, deliver."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Protocol
from pydantic import BaseModel
from oliver_core.report import render_report_html   # existing renderer, unchanged
from oliver_core import audit


# ── Report persistence ──────────────────────────────────────────────────
class ReportStore(Protocol):
    def put(self, submission_id: str, html: str) -> str: ...
    def get(self, ref: str) -> Optional[str]: ...

class MemoryReportStore:
    def __init__(self): self._r: dict[str, str] = {}
    def put(self, sid, html): self._r[sid] = html; return sid
    def get(self, ref): return self._r.get(ref)

class FileReportStore:
    def __init__(self, d): self._d = Path(d); self._d.mkdir(parents=True, exist_ok=True)
    def put(self, sid, html):
        p = self._d / f"{sid}.html"; p.write_text(html); return str(p)
    def get(self, ref):
        p = Path(ref); return p.read_text() if p.exists() else None

_report_store: Optional[ReportStore] = None
def report_store() -> ReportStore:
    global _report_store
    if _report_store is None:
        kind = os.getenv("OLIVER_REPORTS", "memory").lower()
        _report_store = FileReportStore(os.getenv("OLIVER_REPORTS_DIR", "oliver-reports")) if kind in ("file","disk") else MemoryReportStore()
    return _report_store
def reset(): 
    global _report_store, _deliverer
    _report_store = None; _deliverer = None


# ── Email envelope ──────────────────────────────────────────────────────
class AttachmentMeta(BaseModel):
    filename: str
    content_type: str = "text/html"
    size_bytes: int
    report_ref: str                 # bytes live in the report store, fetched by ref at send time

class EmailEnvelope(BaseModel):
    to: str
    subject: str
    body: str                                   # plain-text fallback
    html_body: Optional[str] = None             # the submitter-facing HTML report
    attachments: list[AttachmentMeta] = []

class DeliveryResult(BaseModel):
    delivered: bool
    channel: str
    detail: str = ""


# ── Delivery interface ──────────────────────────────────────────────────
class Deliverer(Protocol):
    def deliver(self, envelope: EmailEnvelope) -> DeliveryResult: ...

class LogDeliverer:
    """Local/default: records the send without an external call."""
    def deliver(self, e): return DeliveryResult(delivered=True, channel="log", detail=f"logged delivery to {e.to}")

class GraphDeliverer:
    """DEPLOYMENT adapter — Microsoft Graph sendMail. Not exercised locally."""
    def __init__(self, sender: Optional[str] = None):
        self._sender = sender or os.getenv("OLIVER_GRAPH_SENDER")
        if not self._sender:
            raise RuntimeError("GraphDeliverer requires OLIVER_GRAPH_SENDER")
    def deliver(self, e) -> DeliveryResult:  # pragma: no cover - deployment
        # SEAM: acquire a managed-identity token, fetch the report from the report
        # store by ref, base64-encode it, and POST to
        # https://graph.microsoft.com/v1.0/users/{sender}/sendMail.
        raise NotImplementedError("GraphDeliverer is wired at deployment (Graph sendMail).")

_deliverer: Optional[Deliverer] = None
def active_deliverer() -> Deliverer:
    global _deliverer
    if _deliverer is None:
        _deliverer = GraphDeliverer() if os.getenv("OLIVER_DELIVERY", "log").lower() == "graph" else LogDeliverer()
    return _deliverer


# ── Orchestration ───────────────────────────────────────────────────────
def deliver_assessment(sub, *, recipient: Optional[str] = None,
                       deliverer: Optional[Deliverer] = None,
                       store: Optional[ReportStore] = None,
                       actor: str = "system") -> DeliveryResult:
    store = store or report_store()
    deliverer = deliverer or active_deliverer()
    from oliver_core.email_report import render_submitter_email
    email_html = render_submitter_email(sub)                    # the Door-A experience (body)
    html = render_report_html(sub)                              # complete record (attachment)
    ref = store.put(str(sub.id), html)
    audit.record("report_rendered", subject=str(sub.id),
                 payload={"report_ref": ref, "bytes": len(html)}, actor=actor)
    env = EmailEnvelope(
        to=recipient or "submitter@pending",
        subject=f"Re: Assessment for Pilot Submission: {sub.input.title}",
        body=sub.assessment.executive_summary,
        html_body=email_html,
        attachments=[AttachmentMeta(filename=f"Oliver-Assessment-{str(sub.id)[:8]}.html",
                                    size_bytes=len(html), report_ref=ref)],
    )
    result = deliverer.deliver(env)
    audit.record("email_sent", subject=str(sub.id),
                 payload={"to": env.to, "channel": result.channel, "delivered": result.delivered,
                          "attachments": [a.filename for a in env.attachments]}, actor=actor)
    return result
