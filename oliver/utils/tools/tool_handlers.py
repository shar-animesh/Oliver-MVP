"""Handlers for Oliver's custom semantic-search tool."""

import json
from typing import Any, Dict, List, Tuple
from uuid import UUID

from openai import OpenAI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from utils.postgres import EmailThreadDb

from .tool_schema import SEARCH_RELATED_IDEAS_TOOL_NAME, SearchRelatedIdeasInput

OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"
OPENAI_EMBEDDING_DIMENSIONS = 1536
INTERNAL_EMAIL_DOMAIN = "siemens-energy.com"
SIMILAR_IDEA_LIMIT = 3
SIMILAR_IDEA_MAX_COSINE_DISTANCE = 0.35


def generate_embedding(client: OpenAI, input_text: str) -> List[float]:
    """Generate one vector for the complete supplied text."""
    response = client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=input_text,
        dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        encoding_format="float",
    )
    return response.data[0].embedding


def handle_tool_call(
    client: OpenAI,
    db: Session,
    current_thread: EmailThreadDb,
    tool_name: str,
    tool_arguments: str,
) -> Tuple[str, List[Tuple[EmailThreadDb, float]]]:
    """Execute one custom tool call and return model context plus matched threads."""
    if tool_name != SEARCH_RELATED_IDEAS_TOOL_NAME:
        return json.dumps({"error": f"Unsupported tool: {tool_name}"}), []

    participant_email = (current_thread.participant_email or "").lower()
    if not participant_email.endswith(f"@{INTERNAL_EMAIL_DOMAIN}"):
        return json.dumps({"results": [], "reason": "Related internal ideas are available only for internal participants."}), []

    arguments = SearchRelatedIdeasInput.model_validate_json(tool_arguments)
    query_embedding = generate_embedding(client, arguments.query)
    rows = db.execute(
        text(
            f"""
            SELECT TOP ({SIMILAR_IDEA_LIMIT})
                id,
                VECTOR_DISTANCE('cosine', embedding, CAST(:query_embedding AS VECTOR(1536))) AS cosine_distance
            FROM email_threads
            WHERE id <> :thread_id
                AND embedding IS NOT NULL
                AND participant_email IS NOT NULL
                AND LOWER(participant_email) LIKE :internal_domain
                AND (:participant_email IS NULL OR participant_email <> :participant_email)
                AND embedding_model = :embedding_model
                AND embedding_dimensions = :embedding_dimensions
                AND VECTOR_DISTANCE('cosine', embedding, CAST(:query_embedding AS VECTOR(1536))) <= :maximum_distance
            ORDER BY cosine_distance ASC
            """
        ),
        {
            "query_embedding": json.dumps(query_embedding, separators=(",", ":")),
            "thread_id": str(current_thread.id),
            "participant_email": current_thread.participant_email,
            "internal_domain": f"%@{INTERNAL_EMAIL_DOMAIN}",
            "embedding_model": OPENAI_EMBEDDING_MODEL,
            "embedding_dimensions": OPENAI_EMBEDDING_DIMENSIONS,
            "maximum_distance": SIMILAR_IDEA_MAX_COSINE_DISTANCE,
        },
    ).all()
    if not rows:
        return json.dumps({"results": []}), []

    thread_ids = [UUID(str(row.id)) for row in rows]
    threads = {candidate.id: candidate for candidate in db.scalars(select(EmailThreadDb).where(EmailThreadDb.id.in_(thread_ids)))}
    matches: List[Tuple[EmailThreadDb, float]] = []
    results: List[Dict[str, Any]] = []
    for row in rows:
        related_thread = threads.get(UUID(str(row.id)))
        if related_thread is None:
            continue
        cosine_distance = float(row.cosine_distance)
        matches.append((related_thread, cosine_distance))
        results.append(
            {
                "contact_email": related_thread.participant_email,
                "subject": related_thread.subject,
                "cosine_distance": round(cosine_distance, 4),
                "participant_authored_email_history": related_thread.semantic_text,
            }
        )

    return json.dumps({"results": results}, ensure_ascii=False), matches
