"""Response model for Oliver's final output."""

from typing import Literal, Optional

from pydantic import BaseModel, model_validator

OliverAction = Literal["SEND_EMAIL", "NO_REPLY"]


class OliverResponse(BaseModel):
    """Structured response returned by Oliver."""

    action: OliverAction
    subject: Optional[str] = None
    content_html: Optional[str] = None

    @model_validator(mode="after")
    def require_email_content_for_send_action(self) -> "OliverResponse":
        """Require the fields needed to deliver an email when Oliver chooses to reply."""
        if self.action == "SEND_EMAIL":
            if self.subject is None or not self.subject.strip():
                raise ValueError("subject is required when action is SEND_EMAIL")
            if self.content_html is None or not self.content_html.strip():
                raise ValueError("content_html is required when action is SEND_EMAIL")
        return self
