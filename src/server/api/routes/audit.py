from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from ...services.audit_service import AuditLogger, AuditResult, truncate_ip
from ..deps import get_audit_logger, get_current_user_id, verify_tools_token

login_router = APIRouter()
me_router = APIRouter()


class AuditLoginRequest(BaseModel):
    user_id: str = Field(min_length=1)
    result: AuditResult
    provider: str = "credentials"
    reason: str | None = None


class AuditEventResponse(BaseModel):
    id: int
    ts: str
    user_id: str
    action: str
    target: str | None = None
    ip_truncated: str | None = None
    user_agent: str | None = None
    result: str
    detail: dict[str, object] | None = None


@login_router.post("/audit/login", dependencies=[Depends(verify_tools_token)])
async def audit_login_endpoint(
    payload: AuditLoginRequest,
    request: Request,
    audit: AuditLogger = Depends(get_audit_logger),
) -> dict[str, str]:
    action = "auth.login.success" if payload.result == "success" else "auth.login.failure"
    await audit.log_async(
        payload.user_id,
        action,
        result=payload.result,
        detail={"provider": payload.provider, "reason": payload.reason},
        request=request,
    )
    return {"status": "ok"}


@me_router.get("/audit/me", response_model=list[AuditEventResponse])
async def audit_me_endpoint(
    action: str | None = Query(default=None),
    since: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> list[AuditEventResponse]:
    rows = await audit.list_for_user_async(user_id, action=action, since=since, limit=limit)
    events: list[AuditEventResponse] = []
    for row in rows:
        detail = json.loads(row.detail_json) if row.detail_json else None
        events.append(
            AuditEventResponse(
                id=row.id,
                ts=row.ts,
                user_id=row.user_id,
                action=row.action,
                target=row.target,
                ip_truncated=truncate_ip(row.ip),
                user_agent=row.user_agent,
                result=row.result,
                detail=detail,
            )
        )
    return events
