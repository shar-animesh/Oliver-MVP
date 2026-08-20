"""Handlers for Oliver's custom semantic-search tool."""

import json
from typing import Any, Dict, List, Tuple

from openai import OpenAI
from sqlalchemy import func, select
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
    distance = EmailThreadDb.embedding.cosine_distance(query_embedding)
    rows = db.execute(
        select(EmailThreadDb, distance.label("cosine_distance"))
        .where(
            EmailThreadDb.id != current_thread.id,
            EmailThreadDb.embedding.is_not(None),
            EmailThreadDb.participant_email.is_not(None),
            func.lower(EmailThreadDb.participant_email).like(f"%@{INTERNAL_EMAIL_DOMAIN}"),
            EmailThreadDb.participant_email != current_thread.participant_email,
            EmailThreadDb.embedding_model == OPENAI_EMBEDDING_MODEL,
            EmailThreadDb.embedding_dimensions == OPENAI_EMBEDDING_DIMENSIONS,
            distance <= SIMILAR_IDEA_MAX_COSINE_DISTANCE,
        )
        .order_by(distance)
        .limit(SIMILAR_IDEA_LIMIT)
    ).all()
    if not rows:
        return json.dumps({"results": []}), []

    matches: List[Tuple[EmailThreadDb, float]] = []
    results: List[Dict[str, Any]] = []
    for related_thread, raw_cosine_distance in rows:
        cosine_distance = float(raw_cosine_distance)
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
