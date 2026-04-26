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
from .runtime import LocalModelChatService, SupportsStreamingReply
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


def resolve_runtime() -> LocalModelChatService:
    settings = get_open_model_settings()
    return LocalModelChatService(
        base_model=settings.open_model_base_model,
        adapter_path=settings.open_model_adapter_path,
        model_revision=settings.open_model_model_revision,
        load_in_4bit=settings.open_model_load_in_4bit,
        max_new_tokens=settings.open_model_max_new_tokens,
        temperature=settings.open_model_temperature,
        top_p=settings.open_model_top_p,
    )


def runtime_ready(runtime: SupportsStreamingReply | None) -> bool:
    if runtime is None:
        return False
    if isinstance(runtime, LocalModelChatService):
        return runtime.is_loaded
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
        if fastapi_app.state.runtime is None:
            resolved_runtime = resolve_runtime()
            if isinstance(resolved_runtime, LocalModelChatService):
                resolved_runtime._ensure_loaded()
            fastapi_app.state.runtime = resolved_runtime
        yield

    app = FastAPI(title="Open Model Chat API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.open_model_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.store = store or ConversationStore(settings.open_model_db_path)
    app.state.runtime = runtime
    app.state.ledger = SendLedger(settings.open_model_ledger_db_path)

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

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/live")
    def live_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready_check(request: Request) -> JSONResponse:
        checks: dict[str, dict[str, object]] = {}
        ready = True

        try:
            request.app.state.store.ping()
            checks["db"] = {"status": "ok"}
        except Exception as exc:
            ready = False
            checks["db"] = {"status": "error", "detail": str(exc)}

        model_is_ready = runtime_ready(request.app.state.runtime)
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
    def gmail_login_endpoint(user_id: str = Depends(get_current_user_id)) -> RedirectResponse:
        try:
            return RedirectResponse(start_gmail_oauth_flow(user_id), status_code=302)
        except Exception as exc:
            raise tool_http_error(exc) from exc

    @app.get("/auth/gmail/callback", dependencies=[Depends(verify_tools_token)])
    def gmail_callback_endpoint(
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
        user_id: str = Depends(get_current_user_id),
    ) -> RedirectResponse:
        _ = user_id
        if error:
            raise HTTPException(status_code=400, detail=f"Gmail OAuth denied: {error}")
        if not code:
            raise HTTPException(status_code=400, detail="Missing Gmail OAuth authorization code.")
        try:
            complete_gmail_oauth_flow(code=code, state=state or "")
        except Exception as exc:
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
    def gmail_logout_endpoint(
        user_id: str = Depends(get_current_user_id),
    ) -> dict[str, object]:
        status_payload = disconnect_gmail(user_id)
        return {
            "connected": status_payload.connected,
            "email": status_payload.email,
            "scopes": status_payload.scopes or [],
        }

    @app.post("/auth/gmail/session-token", dependencies=[Depends(verify_tools_token)])
    def gmail_session_token_endpoint(payload: GmailSessionTokenRequest) -> dict[str, object]:
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
        except Exception as exc:
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
        limit: int = 20,
        unread_only: bool = True,
        user_id: str = Depends(get_current_user_id),
    ) -> list[EmailSummary]:
        try:
            return await email_tools.read_inbox(user_id, limit=limit, unread_only=unread_only)
        except Exception as exc:
            raise tool_http_error(exc) from exc

    @app.get(
        "/tools/email/{uid}",
        response_model=EmailMessage,
        dependencies=[Depends(verify_tools_token)],
    )
    async def tools_email_endpoint(
        uid: str,
        user_id: str = Depends(get_current_user_id),
    ) -> EmailMessage:
        try:
            return await email_tools.get_email(user_id, uid)
        except Exception as exc:
            raise tool_http_error(exc) from exc

    @app.post(
        "/tools/send",
        response_model=SendResult,
        dependencies=[Depends(verify_tools_token)],
    )
    async def tools_send_endpoint(payload: SendRequest) -> SendResult:
        try:
            return await email_tools.send_request(payload)
        except Exception as exc:
            raise tool_http_error(exc) from exc

    @app.post(
        "/agent/run",
        response_model=AgentRunResult,
        dependencies=[Depends(verify_tools_token)],
    )
    async def agent_run_endpoint(
        payload: AgentRunRequest,
        chat_runtime: SupportsStreamingReply = Depends(get_runtime),
        user_id: str = Depends(get_current_user_id),
    ) -> AgentRunResult:
        try:
            return await AgentLoop(chat_runtime).run(
                payload.message,
                system_prompt=payload.system_prompt,
                max_steps=payload.max_steps,
                user_id=user_id,
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
    def list_conversations_endpoint(
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
    ) -> list[ConversationSummary]:
        return conversation_store.list_conversations(user_id)

    @app.post("/conversations", response_model=ConversationSummary, dependencies=chat_dependencies)
    def create_conversation_endpoint(
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
    ) -> ConversationSummary:
        return conversation_store.create_conversation(user_id)

    @app.get(
        "/conversations/{conversation_id}",
        response_model=ConversationDetail,
        dependencies=chat_dependencies,
    )
    def get_conversation_endpoint(
        conversation_id: str,
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
    ) -> ConversationDetail:
        try:
            return conversation_store.get_conversation(conversation_id, user_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found.") from exc

    @app.delete(
        "/conversations/{conversation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=chat_dependencies,
    )
    def delete_conversation_endpoint(
        conversation_id: str,
        conversation_store: ConversationStore = Depends(get_store),
        user_id: str = Depends(get_current_user_id),
    ) -> Response:
        if not conversation_store.delete_conversation(conversation_id, user_id):
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/conversations/{conversation_id}/messages/stream", dependencies=chat_dependencies)
    async def stream_conversation_message(
        conversation_id: str,
        payload: ChatStreamRequest,
        request: Request,
        conversation_store: ConversationStore = Depends(get_store),
        chat_runtime: SupportsStreamingReply = Depends(get_runtime),
        user_id: str = Depends(get_current_user_id),
    ) -> StreamingResponse:
        if not conversation_store.conversation_exists(conversation_id, user_id):
            raise HTTPException(status_code=404, detail="Conversation not found.")

        user_message = conversation_store.save_user_message(conversation_id, user_id, payload.message)
        conversation = conversation_store.get_conversation(conversation_id, user_id)
        summary = conversation_store.get_conversation_summary(conversation_id, user_id)

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
                    yield sse_event("error", ErrorPayload(message=result.answer).model_dump(mode="json"))
                    return

                assistant_message = conversation_store.save_assistant_message(
                    conversation_id,
                    user_id,
                    result.answer,
                    sources=[],
                )
                updated_summary = conversation_store.get_conversation_summary(conversation_id, user_id)
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

                assistant_message = conversation_store.save_assistant_message(
                    conversation_id,
                    user_id,
                    assistant_text,
                    sources=[],
                )
                updated_summary = conversation_store.get_conversation_summary(conversation_id, user_id)

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
