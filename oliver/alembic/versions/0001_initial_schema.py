# Path: alembic/versions/0001_initial_schema.py
# Description: Initial migration creating the complete Oliver database schema.

"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0001"
down_revision: Optional[Union[str, Sequence[str]]] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create the complete Oliver email, run, and semantic-search schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "email_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("participant_email", sa.String(length=320), nullable=True),
        sa.Column("semantic_text", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("internet_message_id", sa.String(length=512), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("sender_email", sa.String(length=320), nullable=True),
        sa.Column("recipient_emails", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internet_message_id", name="uq_email_messages_internet_message_id"),
    )
    op.create_index("ix_email_messages_thread_received", "email_messages", ["thread_id", "received_at"])
    op.create_table(
        "oliver_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("inbound_message_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("generated_content_html", sa.Text(), nullable=True),
        sa.Column("rendered_email_html", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["inbound_message_id"], ["email_messages.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oliver_runs_thread_created", "oliver_runs", ["thread_id", "created_at"])
    op.create_table(
        "oliver_run_related_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("related_thread_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("cosine_distance", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["related_thread_id"], ["email_threads.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["oliver_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "related_thread_id", name="uq_oliver_run_related_thread"),
    )
    op.create_index(
        "ix_oliver_run_related_threads_run_rank",
        "oliver_run_related_threads",
        ["run_id", "rank"],
    )


def downgrade() -> None:
    """Drop all Oliver communication tables."""
    op.drop_index("ix_oliver_run_related_threads_run_rank", table_name="oliver_run_related_threads")
    op.drop_table("oliver_run_related_threads")
    op.drop_index("ix_oliver_runs_thread_created", table_name="oliver_runs")
    op.drop_table("oliver_runs")
    op.drop_index("ix_email_messages_thread_received", table_name="email_messages")
    op.drop_table("email_messages")
    op.drop_table("email_threads")
