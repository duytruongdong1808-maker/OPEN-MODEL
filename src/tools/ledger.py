from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, insert, select, update

from ..server.db import (
    default_ledger_database_url,
    get_session,
    initialize_schema,
    send_approvals,
    send_ledger,
    sqlite_url_from_path,
)
from ..utils import ROOT_DIR
from .schemas import SendRequest

DEFAULT_LEDGER_DB_PATH = ROOT_DIR / "outputs" / "app" / "ledger.sqlite3"


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
    db_path: Path | None = DEFAULT_LEDGER_DB_PATH
    database_url: str | None = None
    _initialized: bool = field(default=False, init=False)
    _initialize_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        if self.database_url is None:
            self.database_url = (
                sqlite_url_from_path(self.db_path)
                if self.db_path is not None
                else default_ledger_database_url()
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

    async def today_count(self) -> int:
        await self.initialize()
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.count())
            .select_from(send_ledger)
            .where(
                send_ledger.c.sent_at >= start.isoformat(timespec="seconds").replace("+00:00", "Z"),
                send_ledger.c.status.in_(["sent", "dry_run"]),
            )
        )
        async with get_session(self.database_url) as session:
            return int((await session.execute(stmt)).scalar_one())

    async def recent_duplicate(
        self, subject: str, first_recipient: str, window_s: int = 60
    ) -> bool:
        await self.initialize()
        since = datetime.now(UTC) - timedelta(seconds=window_s)
        stmt = (
            select(send_ledger.c.id)
            .where(
                send_ledger.c.subject == subject,
                send_ledger.c.first_recipient == first_recipient,
                send_ledger.c.sent_at >= since.isoformat(timespec="seconds").replace("+00:00", "Z"),
                send_ledger.c.status.in_(["sent", "dry_run"]),
            )
            .limit(1)
        )
        async with get_session(self.database_url) as session:
            return (await session.execute(stmt)).first() is not None

    async def duplicate_count_today(self, subject: str, first_recipient: str) -> int:
        await self.initialize()
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.count())
            .select_from(send_ledger)
            .where(
                send_ledger.c.subject == subject,
                send_ledger.c.first_recipient == first_recipient,
                send_ledger.c.sent_at >= start.isoformat(timespec="seconds").replace("+00:00", "Z"),
                send_ledger.c.status.in_(["sent", "dry_run"]),
            )
        )
        async with get_session(self.database_url) as session:
            return int((await session.execute(stmt)).scalar_one())

    async def record(self, status: str, subject: str, first_recipient: str) -> None:
        await self.initialize()
        async with get_session(self.database_url) as session:
            async with session.begin():
                await session.execute(
                    insert(send_ledger).values(
                        sent_at=utcnow_iso(),
                        subject=subject,
                        first_recipient=first_recipient,
                        status=status,
                    )
                )

    async def create_approval(self, req: SendRequest) -> str:
        await self.initialize()
        approval_id = str(uuid4())
        async with get_session(self.database_url) as session:
            async with session.begin():
                await session.execute(
                    insert(send_approvals).values(
                        id=approval_id,
                        created_at=utcnow_iso(),
                        payload_json=req.model_dump_json(),
                        status="pending",
                    )
                )
        return approval_id

    async def get_approval(self, approval_id: str) -> ApprovalRow | None:
        await self.initialize()
        stmt = select(
            send_approvals.c.id,
            send_approvals.c.created_at,
            send_approvals.c.payload_json,
            send_approvals.c.status,
            send_approvals.c.decided_at,
            send_approvals.c.decided_by,
        ).where(send_approvals.c.id == approval_id)
        async with get_session(self.database_url) as session:
            row = (await session.execute(stmt)).mappings().first()
        return ApprovalRow(**dict(row)) if row is not None else None

    async def decide_approval(self, approval_id: str, status: str, decided_by: str) -> ApprovalRow:
        if status not in {"approved", "rejected", "expired"}:
            raise ValueError(f"Unsupported approval status: {status}")
        await self.initialize()
        async with get_session(self.database_url) as session:
            async with session.begin():
                result = await session.execute(
                    update(send_approvals)
                    .where(send_approvals.c.id == approval_id)
                    .values(status=status, decided_at=utcnow_iso(), decided_by=decided_by)
                )
        if not result.rowcount:
            raise KeyError(approval_id)
        row = await self.get_approval(approval_id)
        if row is None:
            raise KeyError(approval_id)
        return row
