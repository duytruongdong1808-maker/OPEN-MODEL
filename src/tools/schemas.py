from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


BODY_CHAR_CAP = 256 * 1024
SNIPPET_CHAR_CAP = 200


class ToolBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class AttachmentMeta(ToolBaseModel):
    filename: str | None = None
    content_type: str = "application/octet-stream"
    size_bytes: int = Field(ge=0)
    content_id: str | None = None
    disposition: str | None = None


class EmailSummary(ToolBaseModel):
    uid: str = Field(min_length=1)
    from_: EmailStr = Field(alias="from")
    to: list[EmailStr] = Field(default_factory=list)
    subject: str = Field(default="", max_length=500)
    date: datetime
    snippet: str = Field(default="", max_length=SNIPPET_CHAR_CAP)
    unread: bool
    has_attachments: bool


class EmailMessage(EmailSummary):
    body_text: str = Field(default="", max_length=BODY_CHAR_CAP)
    body_html: str | None = Field(default=None, max_length=BODY_CHAR_CAP)
    headers: dict[str, str] = Field(default_factory=dict)
    message_id: str = ""
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)
    attachments: list[AttachmentMeta] = Field(default_factory=list)
    truncated: bool = False


class SendRequest(ToolBaseModel):
    to: list[EmailStr] = Field(min_length=1)
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)
    subject: str = Field(min_length=1, max_length=200)
    body_text: str = Field(max_length=BODY_CHAR_CAP)
    body_html: str | None = Field(default=None, max_length=BODY_CHAR_CAP)
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)
    attachments: list[AttachmentMeta] = Field(default_factory=list)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def reject_empty_addresses(cls, value: list[EmailStr]) -> list[EmailStr]:
        if any(not str(address).strip() for address in value):
            raise ValueError("Email addresses cannot be empty.")
        return value


class SendResult(ToolBaseModel):
    status: Literal["sent", "dry_run", "pending_approval", "blocked"]
    message_id: str | None = None
    reason: str | None = None
    approval_id: str | None = None

