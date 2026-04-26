from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ..utils import ROOT_DIR
from .schemas import SendRequest


DEFAULT_LEDGER_DB_PATH = ROOT_DIR / "outputs" / "app" / "chat.sqlite3"


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class ApprovalRow:
    id: str
    created_at: str
    payload_json: str
    status: str
    decided_at: str | None
    decided_by: str | None


@dataclass
class SendLedger:
    db_path: Path = DEFAULT_LEDGER_DB_PATH

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path).expanduser().resolve()
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
                CREATE TABLE IF NOT EXISTS send_ledger (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sent_at TEXT NOT NULL,
                  subject TEXT NOT NULL,
                  first_recipient TEXT NOT NULL,
                  status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS send_approvals (
                  id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  decided_at TEXT,
                  decided_by TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_send_ledger_sent_at ON send_ledger(sent_at);
                CREATE INDEX IF NOT EXISTS idx_send_approvals_status ON send_approvals(status);
                """
            )

    async def today_count(self) -> int:
        return await asyncio.to_thread(self._today_count_sync)

    def _today_count_sync(self) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM send_ledger
                WHERE sent_at >= ? AND status IN ('sent', 'dry_run')
                """,
                (start.isoformat(timespec="seconds").replace("+00:00", "Z"),),
            ).fetchone()
        return int(row["count"])

    async def recent_duplicate(
        self, subject: str, first_recipient: str, window_s: int = 60
    ) -> bool:
        return await asyncio.to_thread(
            self._recent_duplicate_sync, subject, first_recipient, window_s
        )

    def _recent_duplicate_sync(self, subject: str, first_recipient: str, window_s: int) -> bool:
        since = datetime.now(UTC) - timedelta(seconds=window_s)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM send_ledger
                WHERE subject = ? AND first_recipient = ? AND sent_at >= ?
                  AND status IN ('sent', 'dry_run')
                LIMIT 1
                """,
                (
                    subject,
                    first_recipient,
                    since.isoformat(timespec="seconds").replace("+00:00", "Z"),
                ),
            ).fetchone()
        return row is not None

    async def duplicate_count_today(self, subject: str, first_recipient: str) -> int:
        return await asyncio.to_thread(self._duplicate_count_today_sync, subject, first_recipient)

    def _duplicate_count_today_sync(self, subject: str, first_recipient: str) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM send_ledger
                WHERE subject = ? AND first_recipient = ? AND sent_at >= ?
                  AND status IN ('sent', 'dry_run')
                """,
                (
                    subject,
                    first_recipient,
                    start.isoformat(timespec="seconds").replace("+00:00", "Z"),
                ),
            ).fetchone()
        return int(row["count"])

    async def record(self, status: str, subject: str, first_recipient: str) -> None:
        await asyncio.to_thread(self._record_sync, status, subject, first_recipient)

    def _record_sync(self, status: str, subject: str, first_recipient: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO send_ledger (sent_at, subject, first_recipient, status)
                VALUES (?, ?, ?, ?)
                """,
                (utcnow_iso(), subject, first_recipient, status),
            )

    async def create_approval(self, req: SendRequest) -> str:
        return await asyncio.to_thread(self._create_approval_sync, req)

    def _create_approval_sync(self, req: SendRequest) -> str:
        approval_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO send_approvals (id, created_at, payload_json, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (approval_id, utcnow_iso(), req.model_dump_json()),
            )
        return approval_id

    async def get_approval(self, approval_id: str) -> ApprovalRow | None:
        return await asyncio.to_thread(self._get_approval_sync, approval_id)

    def _get_approval_sync(self, approval_id: str) -> ApprovalRow | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, created_at, payload_json, status, decided_at, decided_by
                FROM send_approvals
                WHERE id = ?
                """,
                (approval_id,),
            ).fetchone()
        return ApprovalRow(**dict(row)) if row is not None else None

    async def decide_approval(self, approval_id: str, status: str, decided_by: str) -> ApprovalRow:
        return await asyncio.to_thread(self._decide_approval_sync, approval_id, status, decided_by)

    def _decide_approval_sync(self, approval_id: str, status: str, decided_by: str) -> ApprovalRow:
        if status not in {"approved", "rejected", "expired"}:
            raise ValueError(f"Unsupported approval status: {status}")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE send_approvals
                SET status = ?, decided_at = ?, decided_by = ?
                WHERE id = ?
                """,
                (status, utcnow_iso(), decided_by, approval_id),
            )
        row = self._get_approval_sync(approval_id)
        if row is None:
            raise KeyError(approval_id)
        return row
