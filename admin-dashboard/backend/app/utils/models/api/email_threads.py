"""API response models for the read-only email-thread dashboard."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class EmailMessageResponse(BaseModel):
    """One inbound or outbound message in a conversation."""

    id: UUID
    direction: Literal["INBOUND", "OUTBOUND"]
    sender_email: Optional[str]
    recipient_emails: Optional[str]
    subject: Optional[str]
    content_html: Optional[str]
    received_at: datetime


class RelatedIdeaResponse(BaseModel):
    """One semantic match supplied to an Oliver response."""

    thread_id: UUID
    subject: Optional[str]
    participant_email: Optional[str]
    rank: int
    cosine_distance: float


class OliverRunResponse(BaseModel):
    """One stored Oliver decision for an inbound message."""

    id: UUID
    action: Literal["SEND_EMAIL", "NO_REPLY"]
    model_name: str
    subject: Optional[str]
    related_ideas: List[RelatedIdeaResponse]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    created_at: datetime


class EmailThreadSummaryResponse(BaseModel):
    """Compact thread information displayed in the inbox list."""

    id: UUID
    conversation_id: str
    subject: Optional[str]
    participant_email: Optional[str]
    message_count: int
    last_activity_at: datetime


class EmailThreadDetailResponse(BaseModel):
    """Complete communication history and Oliver decisions for a thread."""

    id: UUID
    conversation_id: str
    subject: Optional[str]
    participant_email: Optional[str]
    embedding_model: Optional[str]
    embedding_dimensions: Optional[int]
    embedded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    messages: List[EmailMessageResponse]
    runs: List[OliverRunResponse]
