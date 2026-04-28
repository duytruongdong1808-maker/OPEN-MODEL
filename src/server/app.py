from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from ..tools import email_tools
from ..tools.gmail_auth import (
    complete_gmail_oauth_flow,
    disconnect_gmail,
    get_gmail_status,
    start_gmail_oauth_flow,
    store_gmail_session_token,
    warn_if_legacy_token_file_exists,
)
from ..tools.ledger import SendLedger
from ..utils import configure_logging
from .api.deps import get_send_ledger
from .api.router import create_api_router
from .core.config import get_open_model_settings
from .core.runtime import SupportsStreamingReply, build_chat_service
from .db import default_database_url, default_ledger_database_url, dispose_engine
from .observability import RequestContextMiddleware, configure_tracing, instrument_fastapi
from .observability.sentry import init_sentry
from .repositories.conversation_store import ConversationStore
from .services.audit_service import AuditLogger
from .services.chat_stream_service import get_web_agent_registry

__all__ = [
    "app",
    "complete_gmail_oauth_flow",
    "create_app",
    "disconnect_gmail",
    "email_tools",
    "get_gmail_status",
    "get_send_ledger",
    "get_web_agent_registry",
    "start_gmail_oauth_flow",
    "store_gmail_session_token",
]


def create_app(
    *,
    store: ConversationStore | None = None,
    runtime: SupportsStreamingReply | None = None,
    protect_chat_routes: bool = True,
) -> FastAPI:
    settings = get_open_model_settings()
    configure_logging(settings.open_model_log_level, settings.open_model_log_format)
    init_sentry(settings)
    tracing_is_enabled = configure_tracing(
        settings.otel_service_name,
        settings.otel_exporter_otlp_endpoint,
        settings.otel_traces_sample_rate,
    )
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
            if hasattr(resolved_runtime, "_ensure_loaded"):
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
    app.add_middleware(RequestContextMiddleware)
    Instrumentator(
        excluded_handlers=["/metrics", "/health.*"],
        should_group_status_codes=True,
    ).instrument(app).expose(app, "/metrics", include_in_schema=False)
    if tracing_is_enabled:
        instrument_fastapi(app)

    app.state.settings = settings
    database_url = default_database_url(settings)
    ledger_database_url = default_ledger_database_url(settings)
    app.state.store = store or ConversationStore(
        settings.open_model_db_path,
        database_url=database_url,
    )
    app.state.runtime = runtime
    app.state.ledger = SendLedger(
        settings.open_model_ledger_db_path,
        database_url=ledger_database_url,
    )
    app.state.audit = AuditLogger(
        settings.open_model_db_path,
        database_url=database_url,
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

    app.include_router(create_api_router(protect_chat_routes=protect_chat_routes))
    return app


app = create_app()
