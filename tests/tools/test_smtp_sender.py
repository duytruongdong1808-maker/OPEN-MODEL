from __future__ import annotations

import json
import logging
from email import policy
from email.parser import BytesParser

import aiosmtplib
import pytest

from src.tools.errors import AuthError, PolicyError
from src.tools.ledger import SendLedger
from src.tools.safety import SafetyPipeline
from src.tools.schemas import AttachmentMeta, SendRequest
from src.tools.smtp_sender import SMTPSender


def request(
    *,
    to: list[str] | None = None,
    subject: str = "Hello from tests",
    body_text: str = "Plain body",
    body_html: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
) -> SendRequest:
    return SendRequest(
        to=to or ["person@example.com"],
        cc=cc or [],
        bcc=bcc or [],
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        in_reply_to=in_reply_to,
        references=references or [],
    )


def parsed_capture(smtp_capture):
    _, _, capture = smtp_capture
    assert capture.envelopes
    return BytesParser(policy=policy.default).parsebytes(capture.envelopes[-1].content)


async def test_send_round_trip_captured(smtp_settings, safety, smtp_capture):
    sender = SMTPSender(smtp_settings, safety)

    result = await sender.send(request())

    message = parsed_capture(smtp_capture)
    assert result.status == "sent"
    assert message["From"] == "Sender <sender@example.com>"
    assert message["To"] == "person@example.com"
    assert message["Subject"] == "Hello from tests"
    assert message["Date"]
    assert message["Message-ID"]


async def test_reply_sets_threading_headers(smtp_settings, safety, smtp_capture):
    sender = SMTPSender(smtp_settings, safety)

    await sender.send(
        request(
            subject="Re: thread",
            in_reply_to="<reply-to@example.com>",
            references=["<root@example.com>"],
        )
    )

    message = parsed_capture(smtp_capture)
    assert message["In-Reply-To"] == "<reply-to@example.com>"
    assert message["References"] == "<root@example.com> <reply-to@example.com>"


async def test_bcc_not_in_headers_but_in_envelope(smtp_settings, safety, smtp_capture):
    sender = SMTPSender(smtp_settings, safety)

    await sender.send(
        request(
            subject="Bcc privacy",
            to=["to@example.com"],
            cc=["cc@example.com"],
            bcc=["secret@example.com"],
        )
    )

    _, _, capture = smtp_capture
    message = parsed_capture(smtp_capture)
    assert "Bcc" not in message
    assert "secret@example.com" in capture.envelopes[-1].rcpt_tos


async def test_multipart_alternative_when_html_provided(smtp_settings, safety, smtp_capture):
    sender = SMTPSender(smtp_settings, safety)

    await sender.send(request(subject="HTML", body_html="<p>HTML body</p>"))

    message = parsed_capture(smtp_capture)
    assert message.get_content_type() == "multipart/alternative"
    assert any(part.get_content_type() == "text/html" for part in message.walk())


async def test_attachment_request_raises_policy_error(smtp_settings, safety):
    sender = SMTPSender(smtp_settings, safety)
    req = request().model_copy(
        update={
            "attachments": [
                AttachmentMeta(filename="x.pdf", content_type="application/pdf", size_bytes=10)
            ]
        }
    )

    with pytest.raises(PolicyError):
        await sender.send(req)


async def test_dry_run_skips_network(tmp_path, smtp_settings, ledger_db, smtp_capture):
    settings = smtp_settings.model_copy(update={"dry_run": True})
    dry_run_log = tmp_path / "agent_dry_run.log"
    safety = SafetyPipeline(
        settings,
        ledger_db,
        dry_run_log_path=dry_run_log,
        safety_log_path=tmp_path / "agent_safety.log",
    )
    sender = SMTPSender(settings, safety)

    result = await sender.send(request())

    _, _, capture = smtp_capture
    assert result.status == "dry_run"
    assert capture.envelopes == []
    line = json.loads(dry_run_log.read_text(encoding="utf-8").splitlines()[0])
    assert line["subject"] == "Hello from tests"
    assert "smtp-secret-not-in-logs" not in dry_run_log.read_text(encoding="utf-8")


async def test_disallowed_domain_blocked(tmp_path, smtp_settings, ledger_db):
    settings = smtp_settings.model_copy(update={"allowed_recipient_domains": ["example.com"]})
    safety_log = tmp_path / "agent_safety.log"
    safety = SafetyPipeline(settings, ledger_db, safety_log_path=safety_log)
    sender = SMTPSender(settings, safety)

    result = await sender.send(request(to=["person@gmail.com"]))

    assert result.status == "blocked"
    assert "domain" in str(result.reason)
    assert "gmail.com" in safety_log.read_text(encoding="utf-8")


async def test_empty_allowlist_blocks_when_not_dry_run(tmp_path, smtp_settings, ledger_db):
    settings = smtp_settings.model_copy(update={"allowed_recipient_domains": []})
    safety = SafetyPipeline(
        settings,
        ledger_db,
        safety_log_path=tmp_path / "agent_safety.log",
    )
    sender = SMTPSender(settings, safety)

    result = await sender.send(request())

    assert result.status == "blocked"
    assert "allowed_recipient_domains" in str(result.reason)


async def test_daily_cap_blocks_n_plus_one(smtp_settings, safety):
    settings = smtp_settings.model_copy(update={"daily_send_cap": 2})
    safety.settings = settings
    sender = SMTPSender(settings, safety)

    assert (await sender.send(request(subject="cap 1"))).status == "sent"
    assert (await sender.send(request(subject="cap 2"))).status == "sent"
    result = await sender.send(request(subject="cap 3"))

    assert result.status == "blocked"
    assert "daily send cap" in str(result.reason)


async def test_dry_run_counts_toward_cap(tmp_path, smtp_settings, ledger_db):
    settings = smtp_settings.model_copy(update={"dry_run": True, "daily_send_cap": 1})
    safety = SafetyPipeline(
        settings,
        ledger_db,
        dry_run_log_path=tmp_path / "agent_dry_run.log",
        safety_log_path=tmp_path / "agent_safety.log",
    )
    sender = SMTPSender(settings, safety)

    assert (await sender.send(request(subject="dry cap 1"))).status == "dry_run"
    result = await sender.send(request(subject="dry cap 2"))

    assert result.status == "blocked"


async def test_self_send_blocked(smtp_settings, safety):
    sender = SMTPSender(smtp_settings, safety)

    result = await sender.send(request(to=["sender@example.com"]))

    assert result.status == "blocked"
    assert "self-send" in str(result.reason)


async def test_duplicate_within_window_blocked(smtp_settings, safety):
    sender = SMTPSender(smtp_settings, safety)

    assert (await sender.send(request(subject="duplicate"))).status == "sent"
    result = await sender.send(request(subject="duplicate"))

    assert result.status == "blocked"
    assert "duplicate" in str(result.reason)


async def test_require_approval_creates_row_and_returns_pending(tmp_path, smtp_settings, ledger_db):
    settings = smtp_settings.model_copy(update={"require_approval": True})
    safety = SafetyPipeline(
        settings,
        ledger_db,
        dry_run_log_path=tmp_path / "agent_dry_run.log",
        safety_log_path=tmp_path / "agent_safety.log",
    )
    sender = SMTPSender(settings, safety)

    result = await sender.send(request(subject="approval"))

    assert result.status == "pending_approval"
    assert result.approval_id is not None
    approval = await ledger_db.get_approval(result.approval_id)
    assert approval is not None
    assert approval.status == "pending"


async def test_auth_failure_raises_auth_error_no_secret(monkeypatch, smtp_settings, safety):
    class FailingSMTP:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            return None

        def supports_extension(self, name):
            return name == "auth"

        async def login(self, user, password):
            raise aiosmtplib.SMTPAuthenticationError(535, f"bad {password}")

    monkeypatch.setattr("src.tools.smtp_sender.aiosmtplib.SMTP", FailingSMTP)
    sender = SMTPSender(smtp_settings, safety)

    with pytest.raises(AuthError) as exc_info:
        await sender.send(request())

    assert "smtp-secret-not-in-logs" not in str(exc_info.value)


async def test_no_secrets_in_logs(caplog, smtp_settings, safety):
    caplog.set_level(logging.DEBUG)
    sender = SMTPSender(smtp_settings, safety)

    await sender.send(request())

    assert "smtp-secret-not-in-logs" not in caplog.text


async def test_context_manager_quits_smtp(monkeypatch, smtp_settings, safety):
    events = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            events.append("connect")

        def supports_extension(self, name):
            return False

        async def quit(self):
            events.append("quit")

    monkeypatch.setattr("src.tools.smtp_sender.aiosmtplib.SMTP", FakeSMTP)

    with pytest.raises(RuntimeError):
        async with SMTPSender(smtp_settings, safety):
            raise RuntimeError("boom")

    assert events == ["connect", "quit"]


async def test_ledger_tables_and_indexes_exist(ledger_db: SendLedger):
    import sqlite3

    await ledger_db.initialize()
    with sqlite3.connect(ledger_db.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert {"send_ledger", "send_approvals"}.issubset(tables)
    assert {"idx_send_ledger_sent_at", "idx_send_approvals_status"}.issubset(indexes)


async def test_safety_log_records_approval_and_blocks(tmp_path, smtp_settings, ledger_db):
    settings = smtp_settings.model_copy(
        update={"require_approval": True, "allowed_recipient_domains": ["example.com"]}
    )
    safety_log = tmp_path / "agent_safety.log"
    safety = SafetyPipeline(settings, ledger_db, safety_log_path=safety_log)
    sender = SMTPSender(settings, safety)

    await sender.send(request(subject="approval log"))
    await sender.send(request(to=["bad@gmail.com"], subject="blocked log"))

    lines = [json.loads(line) for line in safety_log.read_text(encoding="utf-8").splitlines()]
    assert {line["status"] for line in lines} == {"pending_approval", "blocked"}
