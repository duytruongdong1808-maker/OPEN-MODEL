from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from ....agent import AgentStep
from ....agent.loop import build_email_fallback_answer, to_jsonable
from ....tools import email_tools
from ....tools.schemas import EmailMessage, EmailSummary
from ...services.audit_service import AuditLogger
from ..deps import get_audit_logger, get_current_user_id

router = APIRouter(prefix="/mail", tags=["mail"])


class MailInboxResponse(BaseModel):
    messages: list[EmailSummary]


class MailMessageResponse(BaseModel):
    message: EmailMessage


class MailTriageRequest(BaseModel):
    uid: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=1, ge=1, le=20)
    unread_only: bool = True


class MailTriageResponse(BaseModel):
    triage_markdown: str
    steps: list[AgentStep]
    source_uid: str | None = None
    email: EmailMessage | EmailSummary | None = None


@router.get("/inbox", response_model=MailInboxResponse)
async def list_mail_inbox(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    unread_only: bool = Query(default=True),
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> MailInboxResponse:
    messages = await email_tools.read_inbox(user_id=user_id, limit=limit, unread_only=unread_only)
    await audit.log_async(
        user_id,
        "mail.inbox",
        detail={"limit": limit, "unread_only": unread_only, "count": len(messages)},
        request=request,
    )
    return MailInboxResponse(messages=messages)


@router.get("/messages/{uid}", response_model=MailMessageResponse)
async def get_mail_message(
    uid: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> MailMessageResponse:
    message = await email_tools.get_email(user_id=user_id, uid=uid)
    await audit.log_async(user_id, "mail.message", target=uid, request=request)
    return MailMessageResponse(message=message)


@router.post("/triage", response_model=MailTriageResponse)
async def triage_mail(
    payload: MailTriageRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> MailTriageResponse:
    if payload.uid:
        message = await email_tools.get_email(user_id=user_id, uid=payload.uid)
        step = _tool_step(
            index=0,
            tool_name="get_email",
            arguments={"uid": payload.uid},
            result=message,
        )
        triage = build_email_fallback_answer("Summarize this selected email.", [step])
        source_uid = message.uid
        email: EmailMessage | EmailSummary | None = message
    else:
        messages = await email_tools.read_inbox(
            user_id=user_id,
            limit=payload.limit,
            unread_only=payload.unread_only,
        )
        step = _tool_step(
            index=0,
            tool_name="read_inbox",
            arguments={"limit": payload.limit, "unread_only": payload.unread_only},
            result=messages,
        )
        triage = (
            build_email_fallback_answer("Summarize my inbox.", [step])
            if messages
            else _empty_triage()
        )
        source_uid = messages[0].uid if messages else None
        email = messages[0] if messages else None

    await audit.log_async(
        user_id,
        "mail.triage",
        target=source_uid,
        detail={"uid": payload.uid, "limit": payload.limit, "unread_only": payload.unread_only},
        request=request,
    )
    return MailTriageResponse(
        triage_markdown=triage or _empty_triage(),
        steps=[step],
        source_uid=source_uid,
        email=email,
    )


def _tool_step(
    *,
    index: int,
    tool_name: str,
    arguments: dict[str, Any],
    result: EmailMessage | EmailSummary | list[EmailSummary],
) -> AgentStep:
    return AgentStep(
        index=index,
        kind="tool",
        status="ok",
        tool_name=tool_name,
        arguments=arguments,
        result=to_jsonable(result),
    )


def _empty_triage() -> str:
    return "\n".join(
        [
            "Mình chỉ kiểm tra Inbox (INBOX). Không có thư nào được trả về.",
            "**Tóm tắt**",
            "Không có nội dung email để tóm tắt.",
            "",
            "**Ý chính**",
            "- Không có email phù hợp trong inbox.",
            "",
            "**Việc cần làm**",
            "- Không thấy yêu cầu hành động rõ ràng.",
            "",
            "**Mốc thời gian / deadline**",
            "- Không thấy deadline rõ ràng.",
            "",
            "**Người / bên liên quan**",
            "- Không thấy người hoặc tổ chức liên quan.",
            "",
            "**File đính kèm**",
            "- Không thấy file đính kèm.",
        ]
    )
