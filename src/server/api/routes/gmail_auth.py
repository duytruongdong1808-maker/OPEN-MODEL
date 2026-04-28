from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ...services.audit_service import AuditLogger
from ....tools.gmail_auth import GmailSessionToken
from ..deps import get_audit_logger, get_current_user_id, tool_http_error, verify_tools_token

router = APIRouter(dependencies=[Depends(verify_tools_token)])


class GmailSessionTokenRequest(BaseModel):
    user_id: str = Field(min_length=1)
    email: str | None = None
    access_token: str = Field(min_length=1)
    refresh_token: str | None = None
    expires_at: int | None = None
    scope: str | None = None
    token_type: str | None = None
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)


def _app_compat():
    return import_module("src.server.app")


@router.get("/auth/gmail/login")
async def gmail_login_endpoint(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> RedirectResponse:
    try:
        redirect_url = _app_compat().start_gmail_oauth_flow(user_id)
        await audit.log_async(user_id, "gmail.connect.start", request=request)
        return RedirectResponse(redirect_url, status_code=302)
    except Exception as exc:
        await audit.log_async(
            user_id,
            "gmail.connect.failure",
            result="error",
            detail={"reason": str(exc)},
            request=request,
        )
        raise tool_http_error(exc) from exc


@router.get("/auth/gmail/callback")
async def gmail_callback_endpoint(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> RedirectResponse:
    if error:
        await audit.log_async(
            user_id,
            "gmail.connect.failure",
            result="denied",
            detail={"error": error, "state": state},
            request=request,
        )
        raise HTTPException(status_code=400, detail=f"Gmail OAuth denied: {error}")
    if not code:
        await audit.log_async(
            user_id,
            "gmail.connect.failure",
            result="denied",
            detail={"reason": "missing_code", "state": state},
            request=request,
        )
        raise HTTPException(status_code=400, detail="Missing Gmail OAuth authorization code.")
    try:
        connected_user_id = _app_compat().complete_gmail_oauth_flow(code=code, state=state or "")
        await audit.log_async(connected_user_id, "gmail.connect.success", request=request)
    except Exception as exc:
        await audit.log_async(
            user_id,
            "gmail.connect.failure",
            result="error",
            detail={"reason": str(exc), "code": code, "state": state},
            request=request,
        )
        raise tool_http_error(exc) from exc
    return RedirectResponse("/", status_code=302)


@router.get("/auth/gmail/status")
def gmail_status_endpoint(user_id: str = Depends(get_current_user_id)) -> dict[str, object]:
    status_payload = _app_compat().get_gmail_status(user_id)
    return {
        "connected": status_payload.connected,
        "email": status_payload.email,
        "scopes": status_payload.scopes or [],
    }


@router.post("/auth/gmail/logout")
async def gmail_logout_endpoint(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> dict[str, object]:
    status_payload = _app_compat().disconnect_gmail(user_id)
    await audit.log_async(user_id, "gmail.disconnect", request=request)
    return {
        "connected": status_payload.connected,
        "email": status_payload.email,
        "scopes": status_payload.scopes or [],
    }


@router.post("/auth/gmail/session-token")
async def gmail_session_token_endpoint(
    payload: GmailSessionTokenRequest,
    request: Request,
    audit: AuditLogger = Depends(get_audit_logger),
) -> dict[str, object]:
    try:
        status_payload = _app_compat().store_gmail_session_token(
            GmailSessionToken(
                user_id=payload.user_id,
                email=payload.email,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                expires_at=payload.expires_at,
                scope=payload.scope,
                token_type=payload.token_type,
                client_id=payload.client_id,
                client_secret=payload.client_secret,
            )
        )
        await audit.log_async(
            payload.user_id,
            "gmail.connect.success",
            detail={"email": payload.email, "scopes": status_payload.scopes or []},
            request=request,
        )
    except Exception as exc:
        await audit.log_async(
            payload.user_id,
            "gmail.connect.failure",
            result="error",
            detail={"reason": str(exc), "token": payload.access_token},
            request=request,
        )
        raise tool_http_error(exc) from exc
    return {
        "connected": status_payload.connected,
        "email": status_payload.email,
        "scopes": status_payload.scopes or [],
    }
