from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from ...db import get_session, redact_url_in_message
from ...services.chat_stream_service import inference_ready
router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def live_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
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
