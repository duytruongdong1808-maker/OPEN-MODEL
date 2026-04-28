from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException, Request

from ...tools.errors import AuthError, PolicyError, ToolError
from ...tools.ledger import SendLedger
from ..core.config import OpenModelSettings, get_open_model_settings
from ..core.runtime import SupportsStreamingReply
from ..observability import bind_user_context
from ..repositories.conversation_store import ConversationStore
from ..services.audit_service import AuditLogger


def get_store(request: Request) -> ConversationStore:
    return request.app.state.store


def get_runtime(request: Request) -> SupportsStreamingReply:
    runtime = request.app.state.runtime
    if runtime is None:
        raise HTTPException(status_code=503, detail="Model runtime is not loaded.")
    return runtime


def get_app_settings(request: Request) -> OpenModelSettings:
    return request.app.state.settings


def verify_tools_token(authorization: str | None = Header(default=None)) -> None:
    settings = get_open_model_settings()
    expected = settings.agent_ops_token.get_secret_value() if settings.agent_ops_token else None
    if not expected:
        raise HTTPException(status_code=503, detail="AGENT_OPS_TOKEN is not configured.")
    presented = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="Invalid tools bearer token.")


def get_current_user_id(
    request: Request,
    settings: OpenModelSettings = Depends(get_app_settings),
    x_user_id: str | None = Header(default=None),
    x_user_id_sig: str | None = Header(default=None),
) -> str:
    user_id = (x_user_id or "").strip()
    signature = (x_user_id_sig or "").strip().lower()
    if not user_id or not signature:
        raise HTTPException(status_code=401, detail="Missing user identity headers.")

    secret = settings.internal_hmac_secret
    if secret is None:
        raise HTTPException(status_code=503, detail="INTERNAL_HMAC_SECRET is not configured.")

    expected = hmac.new(
        secret.get_secret_value().encode("utf-8"),
        user_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid user identity signature.")
    request.state.user_id = user_id
    bind_user_context(user_id)
    return user_id


def tool_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, PolicyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ToolError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def get_send_ledger(request: Request) -> SendLedger:
    return request.app.state.ledger


def get_audit_logger(request: Request) -> AuditLogger:
    return request.app.state.audit
