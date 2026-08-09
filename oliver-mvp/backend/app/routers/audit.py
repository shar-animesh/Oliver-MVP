"""
Audit trail read endpoints — traceability surfaced.

Read-only views over the append-only audit log: the event trail and an integrity
check that recomputes the hash chain. Governed writes happen at the side-effect
boundaries (assessment, ingest, weight-set activation), never here.
"""

from __future__ import annotations

from fastapi import APIRouter

from oliver_core import audit

router = APIRouter(tags=["audit"])


@router.get("/audit")
async def list_audit_events(limit: int = 200):
    """Return the audit trail (most recent last), capped at `limit`."""
    evs = audit.events()
    return [e.model_dump(mode="json") for e in evs[-limit:]]


@router.get("/audit/verify")
async def verify_audit_chain():
    """Recompute the hash chain; report integrity and the first broken seq if any."""
    ok, first_bad = audit.verify()
    return {"ok": ok, "first_bad_seq": first_bad, "event_count": len(audit.events())}
