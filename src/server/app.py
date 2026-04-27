from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from .audit import AuditLogger, AuditResult, truncate_ip
from .db import (
    default_database_url,
    default_ledger_database_url,
    dispose_engine,
    get_session,
    redact_url_in_message,
)
from ..agent import (
    READ_ONLY_EMAIL_PROTOCOL,
    AgentLoop,
    AgentRunRequest,
    AgentRunResult,
    AgentStep,
    ApprovalDecisionResult,
)
from ..tools.ledger import SendLedger
from ..utils import (
    DEFAULT_SYSTEM_PROMPT,
    configure_logging,
)
from ..tools import email_tools
from ..tools import TOOL_REGISTRY, ToolSpec
from ..tools.errors import AuthError, PolicyError, ToolError
from ..tools.gmail_auth import (
    GmailSessionToken,
    complete_gmail_oauth_flow,
    disconnect_gmail,
    get_gmail_status,
    start_gmail_oauth_flow,
    store_gmail_session_token,
    warn_if_legacy_token_file_exists,
)
from ..tools.schemas import EmailMessage, EmailSummary, SendRequest, SendResult
from .runtime import (
    LocalModelChatService,
    SupportsStreamingReply,
    VLLMChatService,
    build_chat_service,
)
from .schemas import (
    AssistantDeltaPayload,
    ChatStreamRequest,
    ConversationDetail,
    ConversationSummary,
    ErrorPayload,
    MessageCompletePayload,
    MessageStartPayload,
    StepUpdatePayload,
)
from .settings import OpenModelSettings, get_open_model_settings
from .storage import ConversationStore


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


def sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_steps(mode: str) -> list[tuple[str, str]]:
    if mode == "news":
        return [
            ("search", "Searching sources"),
            ("compare", "Comparing articles"),
            ("draft", "Drafting answer"),
        ]
    return [
        ("context", "Reading conversation"),
        ("draft", "Drafting answer"),
    ]


def get_web_agent_registry() -> dict[str, ToolSpec]:
    return {
        "read_inbox": TOOL_REGISTRY["read_inbox"],
        "get_email": TOOL_REGISTRY["get_email"],
    }


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


def subject_hash(subject: str | None) -> str | None:
    if not subject:
        return None
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]


def email_domain(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[1].lower() or None


def first_recipient_domain(recipients: list[str]) -> str | None:
    for recipient in recipients:
        domain = email_domain(recipient)
        if domain:
            return domain
    return None


async def audit_agent_tool_call(
    audit: AuditLogger,
    user_id: str,
    tool_name: str,
    arguments: dict[str, object],
    request: Request,
) -> None:
    await audit.log_async(
        user_id,
        "agent.tool_call",
        target=tool_name,
        detail={"arguments_keys": sorted(str(key) for key in arguments)},
        request=request,
    )
    if tool_name == "send_email":
        recipients = arguments.get("to")
        recipient_list = recipients if isinstance(recipients, list) else []
        target = first_recipient_domain([str(recipient) for recipient in recipient_list])
        await audit.log_async(
            user_id,
            "tool.send_email",
            target=target,
            detail={
                "to_count": len(recipient_list),
                "cc_count": len(arguments.get("cc") or []),
                "bcc_count": len(arguments.get("bcc") or []),
            },
            request=request,
        )


async def inference_ready(runtime: SupportsStreamingReply | None) -> bool:
    if runtime is None:
        return False
    if isinstance(runtime, LocalModelChatService):
        return runtime.is_loaded
    if isinstance(runtime, VLLMChatService):
        return await runtime.check_ready()
    return True


def create_app(
    *,
    store: ConversationStore | None = None,
    runtime: SupportsStreamingReply | None = None,
    protect_chat_routes: bool = True,
) -> FastAPI:
    settings = get_open_model_settings()
    configure_logging(settings.open_model_log_level)
    warn_if_legacy_token_file_exists()

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        await fastapi_app.state.store.initialize()
        await fastapi_app.state.audit.initialize()
        await fastapi_app.state.ledger.initialize()
        if (
            fastapi_app.state.runtime is None
            and not fastapi_app.state.settings.open_model_skip_model_load
        ):
            resolved_runtime = build_chat_service(fastapi_app.state.settings)
            if isinstance(resolved_runtime, LocalModelChatService):
                resolved_runtime._ensure_loaded()
            fastapi_app.state.runtime = resolved_runtime
        try:
            yield
        finally:
            await dispose_engine()

    app = FastAPI(title="Open Model Chat API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.open_model_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.store = store or ConversationStore(
        settings.open_model_db_path,
        database_url=settings.open_model_database_url or default_database_url(settings),
    )
    app.state.runtime = runtime
    app.state.ledger = SendLedger(
        settings.open_model_ledger_db_path,
        database_url=settings.open_model_ledger_database_url
        or default_ledger_database_url(settings),
    )
    app.state.audit = AuditLogger(
        settings.open_model_db_path,
        database_url=settings.open_model_database_url or default_database_url(settings),
    )

    @app.middleware("http")
    async def reject_large_requests(request: Request, call_next):
        app_settings = request.app.state.settings
        max_request_bytes = app_settings.open_model_max_request_bytes
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                request_bytes = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid Content-Length header."}
                )
            if request_bytes > max_request_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request body too large."})
        return await call_next(request)

    chat_dependencies = [Depends(verify_tools_token)] if protect_chat_routes else []

    @app.post("/audit/login", dependencies=[Depends(verify_tools_token)])
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

    @app.get(
        "/audit/me",
        response_model=list[AuditEventResponse],
        dependencies=chat_dependencies,
    )
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

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/live")
    def live_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready_check(request: Request) -> JSONResponse:
        checks: dict[str, dict[str, object]] = {}
        ready = True

        try:
            async with get_session(request.app.state.store.database_url) as session:
                await session.execute(select(1))
            checks["db"] = {"status": "ok"}
        except Exception as exc:
            ready = False
            checks["db"] = {
                "status": "error",
                "detail": redact_url_in_message(str(exc), request.app.state.store.database_url),
            }

        model_is_ready = await inference_ready(request.app.state.runtime)
        checks["model"] = {"status": "ok" if model_is_ready else "not_ready"}
        ready = ready and model_is_ready

        checks["gmail"] = {
            "status": "not_checked",
            "detail": "Gmail status is per-user and requires authenticated user headers.",
        }

        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ok" if ready else "not_ready", "checks": checks},
        )

    @app.get("/auth/gmail/login", dependencies=[Depends(verify_tools_token)])
    async def gmail_login_endpoint(
        request: Request,
        user_id: str = Depends(get_current_user_id),
        audit: AuditLogger = Depends(get_audit_logger),
    ) -> RedirectResponse:
        try:
            redirect_url = start_gmail_oauth_flow(user_id)
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

    @app.get("/auth/gmail/callback", dependencies=[Depends(verify_tools_token)])
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
            connected_user_id = complete_gmail_oauth_flow(code=code, state=state or "")
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

    @app.get("/auth/gmail/status", dependencies=[Depends(verify_tools_token)])
    def gmail_status_endpoint(
        user_id: str = Depends(get_current_user_id),
    ) -> dict[str, object]:
        status_payload = get_gmail_status(user_id)
        return {
            "connected": status_payload.connected,
            "email": status_payload.email,
            "scopes": status_payload.scopes or [],
        }

    @app.post("/auth/gmail/logout", dependencies=[Depends(verify_tools_token)])
    async def gmail_logout_endpoint(
        request: Request,
        user_id: str = Depends(get_current_user_id),
        audit: AuditLogger = Depends(get_audit_logger),
    ) -> dict[str, object]:
        status_payload = disconnect_gmail(user_id)
        await audit.log_async(user_id, "gmail.disconnect", request=request)
        return {
            "connected": status_payload.connected,
            "email": status_payload.email,
            "scopes": status_payload.scopes or [],
        }

    @app.post("/auth/gmail/session-token", dependencies=[Depends(verify_tools_token)])
    async def gmail_session_token_endpoint(
        payload: GmailSessionTokenRequest,
        request: Request,
        audit: AuditLogger = Depends(get_audit_logger),
    ) -> dict[str, object]:
        try:
            status_payload = store_gmail_session_token(
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

    @app.get(
        "/tools/inbox",
        response_model=list[EmailSummary],
        dependencies=[Depends(verify_tools_token)],
    )
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

    @app.get(
        "/tools/email/{uid}",
        response_model=EmailMessage,
        dependencies=[Depends(verify_tools_token)],
    )
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

    @app.post(
        "/tools/send",
        response_model=SendResult,
        dependencies=[Depends(verify_tools_token)],
    )
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

    @app.post(
        "/agent/run",
        response_model=AgentRunResult,
        dependencies=[Depends(verify_tools_token)],
    )
    async def agent_run_endpoint(
        request: Request,
        payload: AgentRunRequest,
        chat_runtime: SupportsStreamingReply = Depends(get_runtime),
        user_id: str = Depends(get_current_user_id),
        audit: AuditLogger = Depends(get_audit_logger),
    ) -> AgentRunResult:
        try:

            async def on_tool_call(tool_name: str, arguments: dict[str, object]) -> None:
                await audit_agent_tool_call(audit, user_id, tool_name, arguments, request)

            return await AgentLoop(chat_runtime).run(
                payload.message,
                system_prompt=payload.system_prompt,
                max_steps=payload.max_steps,
                user_id=user_id,
                on_tool_call=on_tool_call,
            )
        except Exception as exc:
            raise tool_http_error(exc) from exc

    @app.post(
        "/agent/approvals/{approval_id}/approve",
        response_model=ApprovalDecisionResult,
        dependencies=[Depends(verify_tools_token)],
    )
    async def agent_approval_approve_endpoint(
        approval_id: str,
        x_operator: str | None = Header(default=None),
        ledger: SendLedger = Depends(get_send_ledger),
    ) -> ApprovalDecisionResult:
        try:
            row = await ledger.decide_approval(approval_id, "approved", x_operator or "ops")
            return ApprovalDecisionResult(
                id=row.id,
                status=row.status,  # type: ignore[arg-type]
                decided_at=row.decided_at,
                decided_by=row.decided_by,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Approval not found.") from exc

    @app.post(
        "/agent/approvals/{approval_id}/reject",
        response_model=ApprovalDecisionResult,
        dependencies=[Depends(verify_tools_token)],
    )
    async def agent_approval_reject_endpoint(
        approval_id: str,
        x_operator: str | None = Header(default=None),
        ledger: SendLedger = Depends(get_send_ledger),
    ) -> ApprovalDecisionResult:
        try:
            row = await ledger.decide_approval(approval_id, "rejected", x_operator or "ops")
            return ApprovalDecisionResult(
                id=row.id,
                status=row.status,  # type: ignore[arg-type]
                decided_at=row.decided_at,
                decided_by=row.decided_by,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Approval not found.") from exc

    @app.get(
        "/conversations", response_model=list[ConversationSummary], dependencies=chat_dependencies
    )
    async def list_conversations_endpoint(
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
    ) -> list[ConversationSummary]:
        return await conversation_store.list_conversations(user_id)

    @app.post("/conversations", response_model=ConversationSummary, dependencies=chat_dependencies)
    async def create_conversation_endpoint(
        request: Request,
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
        audit: AuditLogger = Depends(get_audit_logger),
    ) -> ConversationSummary:
        conversation = await conversation_store.create_conversation(user_id)
        await audit.log_async(
            user_id, "conversation.create", target=conversation.id, request=request
        )
        return conversation

    @app.get(
        "/conversations/{conversation_id}",
        response_model=ConversationDetail,
        dependencies=chat_dependencies,
    )
    async def get_conversation_endpoint(
        conversation_id: str,
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
    ) -> ConversationDetail:
        try:
            return await conversation_store.get_conversation(conversation_id, user_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found.") from exc

    @app.delete(
        "/conversations/{conversation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=chat_dependencies,
    )
    async def delete_conversation_endpoint(
        request: Request,
        conversation_id: str,
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
        audit: AuditLogger = Depends(get_audit_logger),
    ) -> Response:
        if not await conversation_store.delete_conversation(conversation_id, user_id):
            await audit.log_async(
                user_id,
                "conversation.delete",
                target=conversation_id,
                result="denied",
                request=request,
            )
            raise HTTPException(status_code=404, detail="Conversation not found.")
        await audit.log_async(
            user_id, "conversation.delete", target=conversation_id, request=request
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/conversations/{conversation_id}/messages/stream", dependencies=chat_dependencies)
    async def stream_conversation_message(
        conversation_id: str,
        payload: ChatStreamRequest,
        request: Request,
        conversation_store: ConversationStore = Depends(get_store),
        chat_runtime: SupportsStreamingReply = Depends(get_runtime),
        user_id: str = Depends(get_current_user_id),
        audit: AuditLogger = Depends(get_audit_logger),
    ) -> StreamingResponse:
        if not await conversation_store.conversation_exists(conversation_id, user_id):
            raise HTTPException(status_code=404, detail="Conversation not found.")

        user_message = await conversation_store.save_user_message(
            conversation_id, user_id, payload.message
        )
        conversation = await conversation_store.get_conversation(conversation_id, user_id)
        summary = await conversation_store.get_conversation_summary(conversation_id, user_id)
        await audit.log_async(
            user_id,
            "conversation.stream",
            target=conversation_id,
            detail={"mode": payload.mode, "message_chars": len(payload.message)},
            request=request,
        )

        async def agent_event_stream() -> AsyncIterator[str]:
            yield sse_event(
                "message_start",
                MessageStartPayload(conversation=summary, user_message=user_message).model_dump(
                    mode="json"
                ),
            )

            step_queue: asyncio.Queue[AgentStep] = asyncio.Queue()

            async def on_step(step: AgentStep) -> None:
                await step_queue.put(step)

            agent = AgentLoop(
                chat_runtime,
                registry=get_web_agent_registry(),
                system_protocol=READ_ONLY_EMAIL_PROTOCOL,
            )
            run_task = asyncio.create_task(
                agent.run(
                    payload.message,
                    system_prompt=payload.system_prompt,
                    max_steps=payload.max_steps,
                    on_step=on_step,
                    user_id=user_id,
                    on_tool_call=lambda tool_name, arguments: audit_agent_tool_call(
                        audit, user_id, tool_name, arguments, request
                    ),
                )
            )

            try:
                while not run_task.done():
                    if await request.is_disconnected():
                        run_task.cancel()
                        return
                    try:
                        step = await asyncio.wait_for(step_queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue
                    yield sse_event("agent_step", step.model_dump(mode="json"))

                while not step_queue.empty():
                    step = step_queue.get_nowait()
                    yield sse_event("agent_step", step.model_dump(mode="json"))

                result = await run_task
                if result.stopped_reason == "error":
                    yield sse_event(
                        "error", ErrorPayload(message=result.answer).model_dump(mode="json")
                    )
                    return

                assistant_message = await conversation_store.save_assistant_message(
                    conversation_id,
                    user_id,
                    result.answer,
                    sources=[],
                )
                updated_summary = await conversation_store.get_conversation_summary(
                    conversation_id, user_id
                )
                yield sse_event(
                    "message_complete",
                    MessageCompletePayload(
                        conversation=updated_summary,
                        assistant_message=assistant_message,
                    ).model_dump(mode="json"),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not run_task.done():
                    run_task.cancel()
                yield sse_event("error", ErrorPayload(message=str(exc)).model_dump(mode="json"))

        if payload.mode == "agent":
            return StreamingResponse(
                agent_event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        async def event_stream() -> AsyncIterator[str]:
            yield sse_event(
                "message_start",
                MessageStartPayload(conversation=summary, user_message=user_message).model_dump(
                    mode="json"
                ),
            )

            steps = build_steps(payload.mode)
            if steps:
                first_step_id, first_step_label = steps[0]
                yield sse_event(
                    "step_update",
                    StepUpdatePayload(
                        step_id=first_step_id, label=first_step_label, status="active"
                    ).model_dump(mode="json"),
                )

            generation = None
            assistant_chunks: list[str] = []
            try:
                for step_id, step_label in steps[:-1]:
                    yield sse_event(
                        "step_update",
                        StepUpdatePayload(
                            step_id=step_id, label=step_label, status="complete"
                        ).model_dump(mode="json"),
                    )

                if steps:
                    draft_step_id, draft_step_label = steps[-1]
                    yield sse_event(
                        "step_update",
                        StepUpdatePayload(
                            step_id=draft_step_id, label=draft_step_label, status="active"
                        ).model_dump(mode="json"),
                    )

                generation = chat_runtime.stream_reply(
                    messages=[message.model_dump() for message in conversation.messages],
                    system_prompt=(payload.system_prompt or DEFAULT_SYSTEM_PROMPT).strip(),
                    mode=payload.mode,
                )

                for chunk in generation.chunks:
                    if await request.is_disconnected():
                        generation.cancel()
                        return
                    assistant_chunks.append(chunk)
                    yield sse_event(
                        "assistant_delta",
                        AssistantDeltaPayload(delta=chunk).model_dump(mode="json"),
                    )

                assistant_text = "".join(assistant_chunks).strip()
                if not assistant_text:
                    raise RuntimeError("The model returned an empty response.")

                assistant_message = await conversation_store.save_assistant_message(
                    conversation_id,
                    user_id,
                    assistant_text,
                    sources=[],
                )
                updated_summary = await conversation_store.get_conversation_summary(
                    conversation_id, user_id
                )

                if len(steps) > 1:
                    draft_step_id, draft_step_label = steps[-1]
                    yield sse_event(
                        "step_update",
                        StepUpdatePayload(
                            step_id=draft_step_id, label=draft_step_label, status="complete"
                        ).model_dump(mode="json"),
                    )

                yield sse_event(
                    "message_complete",
                    MessageCompletePayload(
                        conversation=updated_summary,
                        assistant_message=assistant_message,
                    ).model_dump(mode="json"),
                )
            except Exception as exc:
                if generation is not None:
                    generation.cancel()
                yield sse_event("error", ErrorPayload(message=str(exc)).model_dump(mode="json"))

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()
