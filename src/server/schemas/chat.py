from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "active", "complete", "error"]
MessageRole = Literal["user", "assistant"]


class SourceItem(BaseModel):
    title: str
    source: str
    published_at: str | None = None
    url: str


class ChatMessage(BaseModel):
    id: str
    role: MessageRole
    content: str
    created_at: str
    sources: list[SourceItem] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    system_prompt_override: str | None = None
    last_message_preview: str | None = None


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1)
    system_prompt: str | None = None
    mode: str = Field(default="chat")
    max_steps: int = Field(default=5, ge=1, le=10)
    selected_email_uid: str | None = Field(default=None, min_length=1)


class ConversationUpdateRequest(BaseModel):
    system_prompt_override: str | None = Field(default=None, max_length=8000)


class StepUpdatePayload(BaseModel):
    step_id: str
    label: str
    status: StepStatus


class MessageStartPayload(BaseModel):
    conversation: ConversationSummary
    user_message: ChatMessage


class AssistantDeltaPayload(BaseModel):
    delta: str


class MessageCompletePayload(BaseModel):
    conversation: ConversationSummary
    assistant_message: ChatMessage


class ErrorPayload(BaseModel):
    message: str
