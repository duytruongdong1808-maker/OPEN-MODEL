from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import Request

from .storage import utcnow_iso


AuditResult = Literal["success", "denied", "error"]
SENSITIVE_DETAIL_KEYS = {
    "password",
    "token",
    "secret",
    "body_text",
    "body_html",
    "snippet",
    "code",
    "state",
}
SENSITIVE_DETAIL_SUBSTRINGS = {"password", "token", "secret"}
REDACTED = "[REDACTED]"

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


class AuditLogger:
    """Append-only audit log writer.

    The database does not enforce immutability, but application code must treat audit rows as
    append-only: insert new rows, never update or delete them except via the explicit retention
    purge script.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT,
                    ip TEXT,
                    user_agent TEXT,
                    result TEXT NOT NULL CHECK(result IN ('success','denied','error')),
                    detail_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_audit_log_user_ts
                    ON audit_log(user_id, ts DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_log_action_ts
                    ON audit_log(action, ts DESC);
                """
            )

    def log(
        self,
        user_id: str,
        action: str,
        target: str | None = None,
        result: AuditResult = "success",
        detail: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> None:
        try:
            self._log(user_id, action, target, result, detail, request)
        except Exception as exc:
            logger.warning("Audit logging failed for action %s: %s", action, exc)

    async def log_async(
        self,
        user_id: str,
        action: str,
        target: str | None = None,
        result: AuditResult = "success",
        detail: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> None:
        await asyncio.to_thread(self.log, user_id, action, target, result, detail, request)

    def _log(
        self,
        user_id: str,
        action: str,
        target: str | None,
        result: AuditResult,
        detail: dict[str, Any] | None,
        request: Request | None,
    ) -> None:
        detail_json = None
        if detail is not None:
            detail_json = json.dumps(_scrub_detail(detail), ensure_ascii=False, sort_keys=True)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_log (
                    ts,
                    user_id,
                    action,
                    target,
                    ip,
                    user_agent,
                    result,
                    detail_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utcnow_iso(),
                    user_id,
                    action,
                    target,
                    _extract_ip(request),
                    request.headers.get("user-agent") if request is not None else None,
                    result,
                    detail_json,
                ),
            )

    def list_for_user(
        self,
        user_id: str,
        *,
        action: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[AuditRow]:
        clauses = ["user_id = ?"]
        params: list[Any] = [user_id]
        if action:
            clauses.append("action = ?")
            params.append(action)
        if since:
            clauses.append("ts >= ?")
            params.append(since)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, ts, user_id, action, target, ip, user_agent, result, detail_json
                FROM audit_log
                WHERE {" AND ".join(clauses)}
                ORDER BY ts DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [AuditRow(**dict(row)) for row in rows]


def _scrub_detail(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_DETAIL_KEYS or any(
                sensitive in lowered for sensitive in SENSITIVE_DETAIL_SUBSTRINGS
            ):
                scrubbed[key_text] = REDACTED
            else:
                scrubbed[key_text] = _scrub_detail(item)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_detail(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_detail(item) for item in value]
    return value


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
