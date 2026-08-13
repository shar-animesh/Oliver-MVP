"""Read-only admin endpoints for Oliver email communications."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.utils.models.api import (
    EmailMessageResponse,
    EmailThreadDetailResponse,
    EmailThreadSummaryResponse,
    OliverRunResponse,
    RelatedIdeaResponse,
)
from app.utils.postgres import EmailMessageDb, EmailThreadDb, OliverRunDb, OliverRunRelatedThreadDb, get_db

router = APIRouter(prefix="/api/v1/email-threads", tags=["email threads"])


@router.get("", response_model=List[EmailThreadSummaryResponse])
def list_email_threads(database: Session = Depends(get_db)) -> List[EmailThreadSummaryResponse]:  # noqa: B008
    """List email threads by latest activity."""
    message_counts = (
        select(
            EmailMessageDb.thread_id.label("thread_id"),
            func.count(EmailMessageDb.id).label("message_count"),
            func.max(EmailMessageDb.received_at).label("last_activity_at"),
        )
        .group_by(EmailMessageDb.thread_id)
        .subquery()
    )
    rows = database.execute(
        select(EmailThreadDb, message_counts.c.message_count, message_counts.c.last_activity_at)
        .join(message_counts, message_counts.c.thread_id == EmailThreadDb.id)
        .order_by(message_counts.c.last_activity_at.desc())
    ).all()
    return [
        EmailThreadSummaryResponse(
            id=thread.id,
            conversation_id=thread.conversation_id,
            subject=thread.subject,
            participant_email=thread.participant_email,
            message_count=message_count,
            last_activity_at=last_activity_at,
        )
        for thread, message_count, last_activity_at in rows
    ]


@router.get("/{thread_id}", response_model=EmailThreadDetailResponse)
def get_email_thread(
    thread_id: UUID,
    database: Session = Depends(get_db),  # noqa: B008
) -> EmailThreadDetailResponse:
    """Return one complete email conversation and its Oliver decisions."""
    thread = database.scalar(
        select(EmailThreadDb)
        .where(EmailThreadDb.id == thread_id)
        .options(
            selectinload(EmailThreadDb.messages),
            selectinload(EmailThreadDb.runs).selectinload(OliverRunDb.related_threads).selectinload(OliverRunRelatedThreadDb.related_thread),
        )
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email thread not found")

    return EmailThreadDetailResponse(
        id=thread.id,
        conversation_id=thread.conversation_id,
        subject=thread.subject,
        participant_email=thread.participant_email,
        embedding_model=thread.embedding_model,
        embedding_dimensions=thread.embedding_dimensions,
        embedded_at=thread.embedded_at,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[
            EmailMessageResponse(
                id=message.id,
                direction=message.direction,
                sender_email=message.sender_email,
                recipient_emails=message.recipient_emails,
                subject=message.subject,
                content_html=message.content_html,
                received_at=message.received_at,
            )
            for message in thread.messages
        ],
        runs=[
            OliverRunResponse(
                id=run.id,
                action=run.action,
                model_name=run.model_name,
                subject=run.subject,
                related_ideas=[
                    RelatedIdeaResponse(
                        thread_id=match.related_thread.id,
                        subject=match.related_thread.subject,
                        participant_email=match.related_thread.participant_email,
                        rank=match.rank,
                        cosine_distance=match.cosine_distance,
                    )
                    for match in run.related_threads
                ],
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
                created_at=run.created_at,
            )
            for run in thread.runs
        ],
    )
