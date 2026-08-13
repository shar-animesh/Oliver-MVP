"""SQLAlchemy schema for Oliver email conversations and model runs."""

from datetime import datetime
from typing import Any, Callable, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from utils.postgres.base import DatabaseBase


class Vector(UserDefinedType[List[float]]):
    """Azure SQL native vector type transported through pyodbc as JSON."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_kwargs: Any) -> str:
        """Return the Azure SQL column declaration."""
        return f"VECTOR({self.dimensions})"

    def bind_processor(self, _dialect: Any) -> Callable[[Optional[List[float]]], Optional[str]]:
        """Serialize Python vectors for drivers without native vector transport."""
        import json

        def process(value: Optional[List[float]]) -> Optional[str]:
            return json.dumps(value, separators=(",", ":")) if value is not None else None

        return process

    def result_processor(self, _dialect: Any, _coltype: Any) -> Callable[[Any], Optional[List[float]]]:
        """Deserialize Azure SQL's JSON-compatible vector representation."""
        import json

        def process(value: Any) -> Optional[List[float]]:
            if value is None:
                return None
            if isinstance(value, str):
                return [float(component) for component in json.loads(value)]
            return [float(component) for component in value]

        return process


class EmailThreadDb(DatabaseBase):
    """One Microsoft 365 email conversation handled by Oliver."""

    __tablename__ = "email_threads"

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid4)
    conversation_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    participant_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    semantic_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(1536), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.sysdatetimeoffset(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysdatetimeoffset(),
        onupdate=func.sysdatetimeoffset(),
        nullable=False,
    )

    messages: Mapped[List["EmailMessageDb"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="EmailMessageDb.received_at",
    )
    runs: Mapped[List["OliverRunDb"]] = relationship(back_populates="thread", cascade="all, delete-orphan")
    related_run_matches: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="related_thread",
        foreign_keys="OliverRunRelatedThreadDb.related_thread_id",
    )


class EmailMessageDb(DatabaseBase):
    """An inbound or outbound email recorded exactly once."""

    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("internet_message_id", name="uq_email_messages_internet_message_id"),
        Index("ix_email_messages_thread_received", "thread_id", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False)
    internet_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    recipient_emails: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.sysdatetimeoffset(), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="messages")


class OliverRunDb(DatabaseBase):
    """One Oliver decision made for an inbound message."""

    __tablename__ = "oliver_runs"
    __table_args__ = (Index("ix_oliver_runs_thread_created", "thread_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False)
    inbound_message_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_messages.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    generated_content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rendered_email_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.sysdatetimeoffset(), nullable=False)

    thread: Mapped[EmailThreadDb] = relationship(back_populates="runs")
    related_threads: Mapped[List["OliverRunRelatedThreadDb"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="OliverRunRelatedThreadDb.rank",
    )


class OliverRunRelatedThreadDb(DatabaseBase):
    """One related conversation supplied to a specific Oliver run."""

    __tablename__ = "oliver_run_related_threads"
    __table_args__ = (
        UniqueConstraint("run_id", "related_thread_id", name="uq_oliver_run_related_thread"),
        Index("ix_oliver_run_related_threads_run_rank", "run_id", "rank"),
    )

    id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("oliver_runs.id", ondelete="CASCADE"), nullable=False)
    related_thread_id: Mapped[UUID] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("email_threads.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    cosine_distance: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.sysdatetimeoffset(), nullable=False)

    run: Mapped[OliverRunDb] = relationship(back_populates="related_threads")
    related_thread: Mapped[EmailThreadDb] = relationship(
        back_populates="related_run_matches",
        foreign_keys=[related_thread_id],
    )
