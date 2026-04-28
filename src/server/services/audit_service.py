from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import insert, select

from ..db import (
    audit_log,
    default_database_url,
    get_session,
    initialize_schema,
    sqlite_url_from_path,
)
from ..observability.metrics import AUTH_LOGIN_TOTAL, GMAIL_OAUTH_TOTAL
from ..observability.redact import SENSITIVE_KEYS, scrub
from ..repositories.conversation_store import utcnow_iso

AuditResult = Literal["success", "denied", "error"]
SENSITIVE_DETAIL_KEYS = SENSITIVE_KEYS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditRow:
    id: int
    ts: str
    user_id: str
    action: str
    target: str | None
    ip: str | None
    user_agent: str | None
    result: str
    detail_json: str | None


@dataclass
class AuditLogger:
    """Append-only audit log writer."""

    db_path: Path | None = None
    database_url: str | None = None
    _initialized: bool = field(default=False, init=False)
    _initialize_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        if self.database_url is None:
            self.database_url = (
                sqlite_url_from_path(self.db_path)
                if self.db_path is not None
                else default_database_url()
            )
        if self.db_path is not None:
            self.db_path = Path(self.db_path).expanduser().resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if not self._initialized:
                await initialize_schema(self.database_url)
                self._initialized = True

    async def log_async(
        self,
        user_id: str,
        action: str,
        target: str | None = None,
        result: AuditResult = "success",
        detail: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> None:
        try:
            await self._log(user_id, action, target, result, detail, request)
        except Exception as exc:
            logger.warning("Audit logging failed for action %s: %s", action, exc)

    def log(
        self,
        user_id: str,
        action: str,
        target: str | None = None,
        result: AuditResult = "success",
        detail: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> None:
        asyncio.run(self.log_async(user_id, action, target, result, detail, request))

    async def _log(
        self,
        user_id: str,
        action: str,
        target: str | None,
        result: AuditResult,
        detail: dict[str, Any] | None,
        request: Request | None,
    ) -> None:
        await self.initialize()
        scrubbed_detail = _scrub_detail(detail) if detail is not None else None
        stored_detail: Any = scrubbed_detail
        if scrubbed_detail is not None and not str(self.database_url).startswith("postgresql"):
            stored_detail = json.dumps(scrubbed_detail, ensure_ascii=False, sort_keys=True)
        async with get_session(self.database_url) as session:
            async with session.begin():
                await session.execute(
                    insert(audit_log).values(
                        ts=utcnow_iso(),
                        user_id=user_id,
                        action=action,
                        target=target,
                        ip=_extract_ip(request),
                        user_agent=(
                            request.headers.get("user-agent") if request is not None else None
                        ),
                        result=result,
                        detail_json=stored_detail,
                    )
                )
        _record_audit_metric(action, result)

    async def list_for_user_async(
        self,
        user_id: str,
        *,
        action: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[AuditRow]:
        await self.initialize()
        stmt = select(
            audit_log.c.id,
            audit_log.c.ts,
            audit_log.c.user_id,
            audit_log.c.action,
            audit_log.c.target,
            audit_log.c.ip,
            audit_log.c.user_agent,
            audit_log.c.result,
            audit_log.c.detail_json,
        ).where(audit_log.c.user_id == user_id)
        if action:
            stmt = stmt.where(audit_log.c.action == action)
        if since:
            stmt = stmt.where(audit_log.c.ts >= since)
        stmt = stmt.order_by(audit_log.c.ts.desc(), audit_log.c.id.desc()).limit(limit)
        async with get_session(self.database_url) as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [AuditRow(**_audit_row_dict(row)) for row in rows]

    def list_for_user(
        self,
        user_id: str,
        *,
        action: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[AuditRow]:
        return asyncio.run(
            self.list_for_user_async(user_id, action=action, since=since, limit=limit)
        )


def _audit_row_dict(row: Any) -> dict[str, Any]:
    payload = dict(row)
    detail = payload.get("detail_json")
    if detail is not None and not isinstance(detail, str):
        payload["detail_json"] = json.dumps(detail, ensure_ascii=False, sort_keys=True)
    return payload


def _scrub_detail(value: Any) -> Any:
    return scrub(value)


def _record_audit_metric(action: str, result: AuditResult) -> None:
    if action.startswith(("gmail.oauth", "gmail.connect")):
        GMAIL_OAUTH_TOTAL.labels(action=action, result=result).inc()
    if action.startswith("auth.login"):
        AUTH_LOGIN_TOTAL.labels(result=result).inc()


def _extract_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip() or None
    return request.client.host if request.client else None


def truncate_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:2] + ["x", "x"])
    return None
