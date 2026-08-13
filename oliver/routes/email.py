# Path: routes/email.py
# Description: Internal email-response route called by the Logic App.

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError, OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from utils.models import OliverResponse
from utils.models.api import EmailResponseRequest, EmailResponseResult
from utils.postgres import EmailMessageDb, EmailThreadDb, OliverRunDb, OliverRunRelatedThreadDb, get_db
from utils.prompts import build_system_prompt
from utils.security import require_internal_api_key
from utils.templates import render_oliver_email
from utils.tools.tool_handlers import (
    INTERNAL_EMAIL_DOMAIN,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
    generate_embedding,
    handle_tool_call,
)
from utils.tools.tool_schema import TOOL_SCHEMAS

settings = get_settings()

OPENAI_REQUEST_TIMEOUT_SECONDS = 5 * 60
MAX_TOOL_ROUNDS = 8

client = OpenAI(
    api_key=settings.OPENAI_API_KEY.get_secret_value(),
    base_url=settings.OPENAI_BASE_URL,
    timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
)

router = APIRouter(
    prefix="/email",
    tags=["Email"],
    dependencies=[Depends(require_internal_api_key)],
)


@router.post("/respond", response_model=EmailResponseResult)
def respond_to_email(
    request: EmailResponseRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> EmailResponseResult:
    """Persist the inbound email and return Oliver's delivery instruction."""
    inbound_message = db.scalar(select(EmailMessageDb).where(EmailMessageDb.internet_message_id == request.message_id))
    if inbound_message is not None:
        existing_run = db.scalar(
            select(OliverRunDb).where(OliverRunDb.inbound_message_id == inbound_message.id).order_by(OliverRunDb.created_at.desc())
        )
        if existing_run is not None:
            return EmailResponseResult(
                run_id=existing_run.id,
                action=existing_run.action,
                subject=existing_run.subject,
                email_html=existing_run.rendered_email_html,
            )
        thread = inbound_message.thread
    else:
        thread = db.scalar(select(EmailThreadDb).where(EmailThreadDb.conversation_id == request.conversation_id))
        if thread is None:
            thread = EmailThreadDb(
                conversation_id=request.conversation_id,
                subject=request.subject,
                participant_email=request.sender_email,
            )
            db.add(thread)
            db.flush()
        else:
            thread.subject = request.subject or thread.subject
            thread.participant_email = request.sender_email or thread.participant_email

        inbound_message = EmailMessageDb(
            thread_id=thread.id,
            internet_message_id=request.message_id,
            direction="INBOUND",
            sender_email=request.sender_email,
            recipient_emails=request.recipient_emails,
            subject=request.subject,
            content_html=request.email_thread,
            received_at=request.received_at,
        )
        db.add(inbound_message)
        db.commit()
        db.refresh(inbound_message)

    try:
        messages: List[EmailMessageDb] = list(
            db.scalars(select(EmailMessageDb).where(EmailMessageDb.thread_id == thread.id).order_by(EmailMessageDb.received_at.asc()))
        )
        email_thread = "\n\n".join(
            (
                f'<email direction="{message.direction}" sender="{message.sender_email or "unknown"}" '
                f'received-at="{message.received_at.isoformat()}">\n'
                f"{message.content_html or ''}\n"
                "</email>"
            )
            for message in messages
        )

        class EmailTextExtractor(HTMLParser):
            """Extract readable email text for the semantic index."""

            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.parts: List[str] = []

            def handle_data(self, data: str) -> None:
                normalized = " ".join(data.split())
                if normalized:
                    self.parts.append(normalized)

        inbound_idea_transcript: List[str] = []
        for message in messages:
            if message.direction != "INBOUND":
                continue
            extractor = EmailTextExtractor()
            extractor.feed(message.content_html or "")
            inbound_idea_transcript.append(
                f"Sender: {message.sender_email or 'unknown'}\n"
                f"Subject: {message.subject or 'unknown'}\n"
                f"Received: {message.received_at.isoformat()}\n"
                f"Content:\n{'\n'.join(extractor.parts)}"
            )

        thread.semantic_text = "\n\n".join(inbound_idea_transcript)
        participant_email = (thread.participant_email or "").lower()
        if participant_email.endswith(f"@{INTERNAL_EMAIL_DOMAIN}"):
            thread.embedding = generate_embedding(client, thread.semantic_text)
            thread.embedding_model = OPENAI_EMBEDDING_MODEL
            thread.embedding_dimensions = OPENAI_EMBEDDING_DIMENSIONS
            thread.embedded_at = datetime.now(timezone.utc)
        else:
            thread.embedding = None
            thread.embedding_model = None
            thread.embedding_dimensions = None
            thread.embedded_at = None
        db.commit()

        input_items: List[Any] = [
            {
                "role": "user",
                "content": "Resolve the latest inbound message in the supplied email thread.",
            }
        ]
        related_threads: Dict[UUID, Tuple[EmailThreadDb, float]] = {}
        prompt_tokens = 0
        completion_tokens = 0

        for _tool_round in range(MAX_TOOL_ROUNDS):
            model_response = client.responses.parse(
                model=settings.OPENAI_MODEL,
                instructions=build_system_prompt(email_thread=email_thread),
                input=input_items,
                tools=TOOL_SCHEMAS,
                text_format=OliverResponse,
                reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
                include=["web_search_call.action.sources"],
                store=False,
            )
            if model_response.usage is not None:
                prompt_tokens += model_response.usage.input_tokens
                completion_tokens += model_response.usage.output_tokens
            input_items.extend(model_response.output)

            function_calls = [item for item in model_response.output if item.type == "function_call"]
            if not function_calls:
                oliver_response = model_response.output_parsed
                if oliver_response is None:
                    raise RuntimeError("The model returned no parsed Oliver response")
                break

            for function_call in function_calls:
                tool_output, matches = handle_tool_call(
                    client=client,
                    db=db,
                    current_thread=thread,
                    tool_name=function_call.name,
                    tool_arguments=function_call.arguments,
                )
                for related_thread, cosine_distance in matches:
                    previous_match = related_threads.get(related_thread.id)
                    if previous_match is None or cosine_distance < previous_match[1]:
                        related_threads[related_thread.id] = (related_thread, cosine_distance)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": function_call.call_id,
                        "output": tool_output,
                    }
                )
        else:
            raise RuntimeError("Oliver exceeded the maximum number of tool-call rounds")
    except (APIError, RuntimeError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model provider could not complete the request.",
        ) from error

    rendered_email_html: Optional[str] = None
    if oliver_response.action == "SEND_EMAIL":
        rendered_email_html = render_oliver_email(
            subject=cast(str, oliver_response.subject),
            content_html=cast(str, oliver_response.content_html),
        )

    run_id = uuid4()
    run = OliverRunDb(
        id=run_id,
        thread_id=thread.id,
        inbound_message_id=inbound_message.id,
        action=oliver_response.action,
        model_name=settings.OPENAI_MODEL,
        subject=oliver_response.subject,
        generated_content_html=oliver_response.content_html,
        rendered_email_html=rendered_email_html,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    db.add(run)
    for rank, (related_thread, cosine_distance) in enumerate(
        sorted(related_threads.values(), key=lambda related_match: related_match[1]),
        start=1,
    ):
        db.add(
            OliverRunRelatedThreadDb(
                run_id=run_id,
                related_thread_id=related_thread.id,
                rank=rank,
                cosine_distance=cosine_distance,
            )
        )
    if oliver_response.action == "SEND_EMAIL":
        db.add(
            EmailMessageDb(
                thread_id=thread.id,
                internet_message_id=f"oliver-run:{run_id}",
                direction="OUTBOUND",
                sender_email="Oliver",
                recipient_emails=request.sender_email,
                subject=oliver_response.subject,
                content_html=rendered_email_html,
                received_at=datetime.now(timezone.utc),
            )
        )
    db.commit()

    return EmailResponseResult(
        run_id=run.id,
        action=run.action,
        subject=run.subject,
        email_html=run.rendered_email_html,
    )
