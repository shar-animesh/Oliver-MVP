"""HTTP contracts for the Logic App email workflow."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EmailResponseRequest(BaseModel):
    """Complete metadata and content for one inbound email."""

    message_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    subject: Optional[str] = None
    sender_email: Optional[str] = None
    recipient_emails: Optional[str] = None
    received_at: datetime
    email_thread: str = Field(min_length=1)


class EmailResponseResult(BaseModel):
    """Persisted delivery instruction returned to the Logic App."""

    run_id: UUID
    action: Literal["SEND_EMAIL", "NO_REPLY"]
    subject: Optional[str] = None
    email_html: Optional[str] = None
