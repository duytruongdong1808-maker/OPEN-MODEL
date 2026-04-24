from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ..utils import ROOT_DIR
from .config import EmailSettings
from .errors import PolicyError
from .ledger import SendLedger
from .schemas import SendRequest, SendResult


DEFAULT_DRY_RUN_LOG = ROOT_DIR / "outputs" / "agent_dry_run.log"
DEFAULT_SAFETY_LOG = ROOT_DIR / "outputs" / "agent_safety.log"


@dataclass(frozen=True)
class SafetyDecision:
    status: Literal["allowed", "dry_run", "blocked", "pending_approval"]
    reason: str | None = None
    approval_id: str | None = None

    def to_send_result(self) -> SendResult:
        if self.status == "allowed":
            raise ValueError("Allowed decisions do not map directly to SendResult.")
        return SendResult(
            status=self.status,
            reason=self.reason,
            approval_id=self.approval_id,
        )


class SafetyPipeline:
    def __init__(
        self,
        settings: EmailSettings,
        ledger: SendLedger | None = None,
        *,
        dry_run_log_path: Path | None = None,
        safety_log_path: Path | None = None,
    ):
        self.settings = settings
        self.ledger = ledger or SendLedger()
        self.dry_run_log_path = dry_run_log_path or DEFAULT_DRY_RUN_LOG
        self.safety_log_path = safety_log_path or DEFAULT_SAFETY_LOG

    async def evaluate(self, req: SendRequest) -> SafetyDecision:
        first_recipient = str(req.to[0])
        if req.attachments:
            raise PolicyError("Phase 2 does not send attachments.")

        blocked_reason = self._domain_block_reason(req)
        if blocked_reason:
            await self._record_block(req, blocked_reason)
            return SafetyDecision(status="blocked", reason=blocked_reason)

        blocked_reason = await self._loop_block_reason(req)
        if blocked_reason:
            await self._record_block(req, blocked_reason)
            return SafetyDecision(status="blocked", reason=blocked_reason)

        if await self.ledger.today_count() >= self.settings.daily_send_cap:
            reason = "daily send cap exceeded"
            await self._record_block(req, reason)
            return SafetyDecision(status="blocked", reason=reason)

        if self.settings.dry_run:
            await self._append_jsonl(
                self.dry_run_log_path,
                {
                    "timestamp": self._now(),
                    "status": "dry_run",
                    "to": [str(item) for item in req.to],
                    "cc": [str(item) for item in req.cc],
                    "bcc": [str(item) for item in req.bcc],
                    "subject": req.subject,
                    "body_text": req.body_text,
                    "body_html": req.body_html,
                    "in_reply_to": req.in_reply_to,
                    "references": req.references,
                },
            )
            await self.ledger.record("dry_run", req.subject, first_recipient)
            await self._log_event("dry_run", "dry_run", req)
            return SafetyDecision(status="dry_run", reason="dry-run enabled")

        if self.settings.require_approval:
            approval_id = await self.ledger.create_approval(req)
            await self._log_event("approval", "pending_approval", req, approval_id=approval_id)
            return SafetyDecision(
                status="pending_approval",
                reason="approval required",
                approval_id=approval_id,
            )

        return SafetyDecision(status="allowed")

    async def record_sent(self, req: SendRequest) -> None:
        await self.ledger.record("sent", req.subject, str(req.to[0]))
        await self._log_event("send", "sent", req)

    def _domain_block_reason(self, req: SendRequest) -> str | None:
        allowed = set(self.settings.allowed_recipient_domains)
        if not allowed:
            return None
        for address in self._all_recipients(req):
            domain = address.rsplit("@", 1)[-1].lower()
            if domain not in allowed:
                return f"recipient domain not allowed: {domain}"
        return None

    async def _loop_block_reason(self, req: SendRequest) -> str | None:
        recipients = {address.lower() for address in self._all_recipients(req)}
        if self.settings.smtp_user.lower() in recipients:
            return "self-send blocked"
        first_recipient = str(req.to[0])
        if await self.ledger.recent_duplicate(req.subject, first_recipient, window_s=60):
            return "duplicate send within 60s"
        if await self.ledger.duplicate_count_today(req.subject, first_recipient) >= 5:
            return "duplicate send limit exceeded"
        return None

    async def _record_block(self, req: SendRequest, reason: str) -> None:
        await self.ledger.record("blocked", req.subject, str(req.to[0]))
        await self._log_event("block", "blocked", req, reason=reason)

    async def _log_event(
        self,
        action: str,
        status: str,
        req: SendRequest,
        *,
        reason: str | None = None,
        approval_id: str | None = None,
    ) -> None:
        await self._append_jsonl(
            self.safety_log_path,
            {
                "timestamp": self._now(),
                "action": action,
                "status": status,
                "reason": reason,
                "approval_id": approval_id,
                "recipient_domains": sorted({address.rsplit("@", 1)[-1].lower() for address in self._all_recipients(req)}),
                "subject_len": len(req.subject),
            },
        )

    @staticmethod
    def _all_recipients(req: SendRequest) -> list[str]:
        return [str(item) for item in [*req.to, *req.cc, *req.bcc]]

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    async def _append_jsonl(path: Path, payload: dict) -> None:
        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

        await asyncio.to_thread(write)

