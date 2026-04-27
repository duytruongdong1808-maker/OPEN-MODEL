from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def bind_user_context(user_id: str) -> None:
    structlog.contextvars.bind_contextvars(user_id=user_id)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        structlog.contextvars.clear_contextvars()
        request_id = uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        logger = structlog.get_logger("open_model.access")
        started_at = time.perf_counter()
        status_code = 500
        response_bytes: int | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                structlog.contextvars.bind_contextvars(user_id=user_id)
            response.headers["X-Request-Id"] = request_id
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    response_bytes = int(content_length)
                except ValueError:
                    response_bytes = None
            return response
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "http.request",
                status=status_code,
                duration_ms=round(duration_ms, 2),
                response_bytes=response_bytes,
            )
            structlog.contextvars.clear_contextvars()
