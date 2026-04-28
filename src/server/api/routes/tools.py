from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ....tools import email_tools
from ....tools.schemas import EmailMessage, EmailSummary, SendRequest, SendResult
from ...services.audit_service import AuditLogger
from ...services.email_audit_service import email_domain, first_recipient_domain, subject_hash
from ..deps import get_audit_logger, get_current_user_id, tool_http_error, verify_tools_token
router = APIRouter(dependencies=[Depends(verify_tools_token)])


@router.get("/tools/inbox", response_model=list[EmailSummary])
async def tools_inbox_endpoint(
    request: Request,
    limit: int = 20,
    unread_only: bool = True,
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> list[EmailSummary]:
    try:
        items = await email_tools.read_inbox(user_id, limit=limit, unread_only=unread_only)
        await audit.log_async(
            user_id,
            "gmail.read_inbox",
            target="INBOX",
            detail={
                "limit": limit,
                "unread_only": unread_only,
                "count_returned": len(items),
            },
            request=request,
        )
        return items
    except Exception as exc:
        await audit.log_async(
            user_id,
            "gmail.read_inbox",
            target="INBOX",
            result="error",
            detail={"limit": limit, "unread_only": unread_only, "error": str(exc)},
            request=request,
        )
        raise tool_http_error(exc) from exc


@router.get("/tools/email/{uid}", response_model=EmailMessage)
async def tools_email_endpoint(
    request: Request,
    uid: str,
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> EmailMessage:
    try:
        message = await email_tools.get_email(user_id, uid)
        await audit.log_async(
            user_id,
            "gmail.get_email",
            target=uid,
            detail={
                "subject_hash": subject_hash(message.subject),
                "from_domain": email_domain(message.from_),
            },
            request=request,
        )
        return message
    except Exception as exc:
        await audit.log_async(
            user_id,
            "gmail.get_email",
            target=uid,
            result="error",
            detail={"error": str(exc)},
            request=request,
        )
        raise tool_http_error(exc) from exc


@router.post("/tools/send", response_model=SendResult)
async def tools_send_endpoint(
    payload: SendRequest,
    request: Request,
    audit: AuditLogger = Depends(get_audit_logger),
) -> SendResult:
    target = first_recipient_domain(payload.to)
    try:
        result = await email_tools.send_request(payload)
        await audit.log_async(
            "ops",
            "tool.send_email",
            target=target,
            detail={
                "to_count": len(payload.to),
                "cc_count": len(payload.cc),
                "bcc_count": len(payload.bcc),
                "status": result.status,
            },
            request=request,
        )
        return result
    except Exception as exc:
        await audit.log_async(
            "ops",
            "tool.send_email",
            target=target,
            result="error",
            detail={"error": str(exc), "to_count": len(payload.to)},
            request=request,
        )
        raise tool_http_error(exc) from exc
