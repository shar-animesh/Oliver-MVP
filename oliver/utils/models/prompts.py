"""Response model for Oliver's final output."""

from typing import Literal, Optional

from pydantic import BaseModel

OliverAction = Literal["SEND_EMAIL", "NO_REPLY"]


class OliverResponse(BaseModel):
    """Structured response returned by Oliver."""

    action: OliverAction
    subject: Optional[str] = None
    content_html: Optional[str] = None
