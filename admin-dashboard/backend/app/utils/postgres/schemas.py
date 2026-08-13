"""Read-only mapping of the tables owned and migrated by Oliver."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class DatabaseBase(DeclarativeBase):
    """Local mapping base; the admin service never creates these tables."""


class EmailThreadDb(DatabaseBase):
    """Read-only email conversation mapping."""

    __tablename__ = "email_threads"

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    participant_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    semantic_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    messages: Mapped[List["EmailMessageDb"]] = relationship(
        back_populates="thread",
        order_by="EmailMessageDb.received_at",
    )
    runs: Mapped[List["OliverRunDb"]] = relationship(back_populates="thread", order_by="OliverRunDb.created_at")
    related_run_matches: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="related_thread",
        foreign_keys="OliverRunRelatedThreadDb.related_thread_id",
    )


class EmailMessageDb(DatabaseBase):
    """Read-only inbound or outbound message mapping."""

    __tablename__ = "email_messages"

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    thread_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_threads.id"), nullable=False)
    internet_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    recipient_emails: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="messages")


class OliverRunDb(DatabaseBase):
    """Read-only Oliver decision mapping."""

    __tablename__ = "oliver_runs"

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    thread_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_threads.id"), nullable=False)
    inbound_message_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_messages.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    generated_content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rendered_email_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="runs")
    related_threads: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="run",
        order_by="OliverRunRelatedThreadDb.rank",
    )


class OliverRunRelatedThreadDb(DatabaseBase):
    """Read-only related-conversation match for one Oliver decision."""

    __tablename__ = "oliver_run_related_threads"

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    run_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("oliver_runs.id"), nullable=False)
    related_thread_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_threads.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    cosine_distance: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="related_threads")
    related_thread: Mapped[EmailThreadDb] = relationship(
        back_populates="related_run_matches",
        foreign_keys=[related_thread_id],
    )
