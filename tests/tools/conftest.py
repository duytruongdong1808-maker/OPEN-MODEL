from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path
import socket

import pytest
from aiosmtpd.controller import Controller

from src.tools.config import EmailSettings
from src.tools.ledger import SendLedger
from src.tools.safety import SafetyPipeline


FIXTURES = Path(__file__).parent / "fixtures"


def load_eml(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@dataclass
class FakeFetchResponse:
    result: str
    lines: list[bytes]


def _header_bytes(raw: bytes) -> bytes:
    separator = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
    return raw.split(separator, 1)[0] + separator


def _snippet(raw: bytes) -> bytes:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    parts = parsed.walk() if parsed.is_multipart() else [parsed]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() == "text/plain":
            return str(part.get_content()).encode("utf-8")[:200]
    return b""


def seed_mailbox() -> dict[int, tuple[bytes, set[str]]]:
    return {
        1: (load_eml("plain_text.eml"), set()),
        2: (load_eml("multipart_alternative.eml"), {"\\Seen"}),
        3: (load_eml("utf8_subject_vi.eml"), set()),
        4: (load_eml("latin1_body.eml"), set()),
        5: (load_eml("with_attachments.eml"), set()),
        6: (load_eml("threaded_reply.eml"), set()),
        7: (load_eml("long_body.eml"), set()),
    }


class FakeIMAP:
    def __init__(self, mailbox: dict[int, tuple[bytes, set[str]]]):
        self._mb = {uid: (raw, set(flags)) for uid, (raw, flags) in mailbox.items()}
        self.logged_in = False
        self.selected: str | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.capabilities = {b"IMAP4rev1", b"MOVE"}
        self.fail_login = False
        self.login_args: tuple[str, str] | None = None

    async def wait_hello_from_server(self):
        self.calls.append(("wait_hello_from_server", ()))
        return ("OK", [b""])

    async def login(self, user, pwd):
        self.calls.append(("login", (user, pwd)))
        self.login_args = (user, pwd)
        if self.fail_login:
            return ("NO", [b"authentication failed"])
        self.logged_in = True
        return ("OK", [b""])

    async def logout(self):
        self.calls.append(("logout", ()))
        self.logged_in = False
        return ("OK", [b""])

    async def select(self, mbox):
        self.calls.append(("select", (mbox,)))
        self.selected = mbox
        return ("OK", [f"{len(self._mb)}".encode()])

    async def capability(self):
        self.calls.append(("capability", ()))
        return ("OK", [b"CAPABILITY " + b" ".join(sorted(self.capabilities))])

    async def uid_search(self, *criteria):
        self.calls.append(("uid_search", criteria))
        criterion = " ".join(str(item).upper() for item in criteria)
        uids = []
        for uid, (_, flags) in sorted(self._mb.items()):
            if "UNSEEN" in criterion and "\\Seen" in flags:
                continue
            uids.append(str(uid))
        return ("OK", [" ".join(uids).encode()])

    async def uid(self, cmd, *args):
        self.calls.append(("uid", (cmd, *args)))
        command = str(cmd).upper()
        if command == "FETCH":
            uid_set, items = str(args[0]), str(args[1])
            uids = [int(uid) for uid in uid_set.replace(",", " ").split() if uid]
            if "BODY.PEEK[HEADER]" in items:
                return FakeFetchResponse("OK", self._summary_lines(uids))
            if "BODY.PEEK[]" in items or "RFC822" in items:
                uid = uids[0]
                raw = self._mb[uid][0]
                return FakeFetchResponse("OK", [f"* 1 FETCH (UID {uid} BODY.PEEK[] {{{len(raw)}}}".encode(), raw, b")"])
        if command == "STORE":
            uid = int(args[0])
            flags = self._mb[uid][1]
            flag_text = " ".join(str(arg) for arg in args[1:])
            if "\\Seen" in flag_text:
                flags.add("\\Seen")
            if "\\Deleted" in flag_text:
                flags.add("\\Deleted")
            return ("OK", [b""])
        if command == "MOVE":
            self._mb.pop(int(args[0]), None)
            return ("OK", [b""])
        if command == "COPY":
            return ("OK", [b""])
        if command == "EXPUNGE":
            return await self.expunge()
        raise AssertionError(f"Unexpected UID command: {cmd} {args}")

    async def expunge(self):
        self.calls.append(("expunge", ()))
        deleted = [uid for uid, (_, flags) in self._mb.items() if "\\Deleted" in flags]
        for uid in deleted:
            self._mb.pop(uid, None)
        return ("OK", [b""])

    def flags_for(self, uid: int) -> set[str]:
        return set(self._mb[uid][1])

    def _summary_lines(self, uids: list[int]) -> list[bytes]:
        lines: list[bytes] = []
        for position, uid in enumerate(uids, start=1):
            raw, flags = self._mb[uid]
            flags_text = " ".join(sorted(flags))
            header = _header_bytes(raw)
            snippet = _snippet(raw)
            lines.extend(
                [
                    f"* {position} FETCH (UID {uid} FLAGS ({flags_text}) RFC822.SIZE {len(raw)} BODY[HEADER] {{{len(header)}}}".encode(),
                    header,
                    f" BODY[1]<0> {{{len(snippet)}}}".encode(),
                    snippet,
                    b")",
                ]
            )
        return lines


@pytest.fixture
def email_settings(fake_imap) -> EmailSettings:
    return EmailSettings(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="reader@example.com",
        imap_pass="s3cr3t-not-in-logs",
        imap_mailbox="INBOX",
        archive_mailbox="Archive",
        smtp_host="smtp.example.com",
        smtp_user="reader@example.com",
        smtp_pass="smtp-secret",
        smtp_from="reader@example.com",
    )


@pytest.fixture
def fake_imap(monkeypatch):
    instance = FakeIMAP(seed_mailbox())
    monkeypatch.setattr("src.tools.email_client.aioimaplib.IMAP4_SSL", lambda *args, **kwargs: instance)
    return instance


class CaptureSMTP:
    def __init__(self):
        self.envelopes = []

    async def handle_DATA(self, server, session, envelope):
        self.envelopes.append(envelope)
        return "250 OK"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def smtp_capture():
    capture = CaptureSMTP()
    controller = Controller(capture, hostname="127.0.0.1", port=_free_port())
    controller.start()
    try:
        yield controller.hostname, controller.port, capture
    finally:
        controller.stop()


@pytest.fixture
def ledger_db(tmp_path) -> SendLedger:
    return SendLedger(tmp_path / "send-ledger.sqlite3")


@pytest.fixture
def smtp_settings(smtp_capture) -> EmailSettings:
    host, port, _ = smtp_capture
    return EmailSettings(
        imap_host="imap.example.com",
        imap_user="reader@example.com",
        imap_pass="imap-secret",
        smtp_host=host,
        smtp_port=port,
        smtp_user="sender@example.com",
        smtp_pass="smtp-secret-not-in-logs",
        smtp_from="Sender <sender@example.com>",
        smtp_starttls=False,
        dry_run=False,
        require_approval=False,
        daily_send_cap=20,
    )


@pytest.fixture
def safety(tmp_path, smtp_settings, ledger_db) -> SafetyPipeline:
    return SafetyPipeline(
        smtp_settings,
        ledger_db,
        dry_run_log_path=tmp_path / "agent_dry_run.log",
        safety_log_path=tmp_path / "agent_safety.log",
    )
