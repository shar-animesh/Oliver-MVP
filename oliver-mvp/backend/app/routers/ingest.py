"""
Ingestion endpoint — a thin host over the shared oliver_core.ingest handler.

This is the same handler the Azure Function calls; Power Automate can POST to
either. Kept deliberately thin: parse → delegate → map status to HTTP code.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import require_ingest_client
from oliver_core.ingest import InboundEmail, ingest_email

router = APIRouter(tags=["ingest"])


@router.post("/ingest/email")
async def ingest_email_endpoint(
    email: InboundEmail,
    response: Response,
    client: str = Depends(require_ingest_client),
):
    """
    Accept an inbound email (as Power Automate posts it), assess it idempotently,
    and persist. Returns 201 when a new record is created, 200 when the message-id
    was already ingested (duplicate — no re-assessment).

    Protected: requires a valid bearer token when OLIVER_REQUIRE_AUTH is on
    (see app.auth.require_ingest_client). The authenticated caller is recorded on
    the audit trail as the acting client.
    """
    try:
        result = await ingest_email(email, actor=client)
    except ValueError as e:
        # Email had no assessable content after cleaning.
        raise HTTPException(status_code=422, detail=str(e))

    response.status_code = 201 if result.status == "created" else 200
    return result
