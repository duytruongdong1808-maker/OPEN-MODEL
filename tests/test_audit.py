from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.server.app import create_app
from src.server.audit import AuditLogger
from src.server.runtime import GenerationStream
from src.server.settings import get_open_model_settings
from src.server.storage import ConversationStore
from src.tools.schemas import EmailSummary


TEST_INTERNAL_HMAC_SECRET = "test-internal-hmac-secret-at-least-32-bytes"


class FakeChatRuntime:
    def stream_reply(self, *, messages, system_prompt: str, mode: str = "chat") -> GenerationStream:
        return GenerationStream(chunks=iter(["ok"]), cancel=lambda: None)


def user_headers(user_id: str) -> dict[str, str]:
    signature = hmac.new(
        TEST_INTERNAL_HMAC_SECRET.encode("utf-8"),
        user_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"X-User-Id": user_id, "X-User-Id-Sig": signature}


def configure_env(monkeypatch, tmp_path: Path) -> None:
    get_open_model_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", TEST_INTERNAL_HMAC_SECRET)
    monkeypatch.setenv("AGENT_OPS_TOKEN", "test-token")
    monkeypatch.setenv("OPEN_MODEL_DB_PATH", str(tmp_path / "chat.sqlite3"))


def tools_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def read_audit_rows(db_path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()


def test_audit_redacts_sensitive_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.sqlite3"
    audit = AuditLogger(db_path)

    audit.log(
        "user-a",
        "test.action",
        detail={
            "password": "foo",
            "nested": {"token": "bar", "access_token": "baz", "ok": "kept"},
            "items": [{"body_text": "secret mail"}],
        },
    )

    detail = json.loads(read_audit_rows(db_path)[0]["detail_json"])
    assert detail["password"] == "[REDACTED]"
    assert detail["nested"]["token"] == "[REDACTED]"
    assert detail["nested"]["access_token"] == "[REDACTED]"
    assert detail["nested"]["ok"] == "kept"
    assert detail["items"][0]["body_text"] == "[REDACTED]"


def test_audit_log_isolates_users(tmp_path: Path, monkeypatch) -> None:
    configure_env(monkeypatch, tmp_path)
    store = ConversationStore(tmp_path / "chat.sqlite3")
    app = create_app(store=store, runtime=FakeChatRuntime(), protect_chat_routes=False)
    app.state.audit.log("user-a", "conversation.create", target="a")
    app.state.audit.log("user-b", "conversation.create", target="b")
    client = TestClient(app, headers=user_headers("user-a"))

    response = client.get("/audit/me")

    assert response.status_code == 200
    payload = response.json()
    assert [row["target"] for row in payload] == ["a"]
    assert "ip" not in payload[0]


def test_gmail_read_inbox_emits_audit_with_no_body(tmp_path: Path, monkeypatch) -> None:
    configure_env(monkeypatch, tmp_path)

    async def fake_read_inbox(user_id: str, limit: int = 20, unread_only: bool = True):
        return [
            EmailSummary(
                uid="1",
                **{"from": "alice@example.com"},
                to=["reader@example.com"],
                subject="Sensitive subject",
                date=datetime.now(timezone.utc),
                snippet="body-ish snippet",
                unread=True,
                has_attachments=False,
            )
        ]

    monkeypatch.setattr("src.server.app.email_tools.read_inbox", fake_read_inbox)
    store = ConversationStore(tmp_path / "chat.sqlite3")
    app = create_app(store=store, runtime=FakeChatRuntime(), protect_chat_routes=False)
    client = TestClient(app, headers=user_headers("user-a"))

    response = client.get(
        "/tools/inbox?limit=5&unread_only=false",
        headers={**user_headers("user-a"), **tools_headers()},
    )

    assert response.status_code == 200
    rows = read_audit_rows(tmp_path / "chat.sqlite3")
    row = rows[-1]
    assert row["action"] == "gmail.read_inbox"
    detail = json.loads(row["detail_json"])
    assert detail == {"count_returned": 1, "limit": 5, "unread_only": False}
    assert "body" not in row["detail_json"]
    assert "snippet" not in row["detail_json"]


def test_failed_login_emits_audit_with_no_password(tmp_path: Path, monkeypatch) -> None:
    configure_env(monkeypatch, tmp_path)
    app = create_app(
        store=ConversationStore(tmp_path / "chat.sqlite3"),
        runtime=FakeChatRuntime(),
        protect_chat_routes=False,
    )
    client = TestClient(app)

    response = client.post(
        "/audit/login",
        headers=tools_headers(),
        json={
            "user_id": "bad-user",
            "result": "denied",
            "provider": "credentials",
            "reason": "invalid_credentials",
            "password": "not accepted by schema",
        },
    )

    assert response.status_code == 200
    row = read_audit_rows(tmp_path / "chat.sqlite3")[-1]
    assert row["action"] == "auth.login.failure"
    assert "password" not in (row["detail_json"] or "")
    assert "invalid_credentials" in (row["detail_json"] or "")


def test_audit_purge_respects_days(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.sqlite3"
    AuditLogger(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    old = (
        datetime.now(timezone.utc) - timedelta(days=120)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO audit_log (ts, user_id, action, result)
            VALUES (?, ?, ?, ?)
            """,
            (old, "user-a", "old.action", "success"),
        )
        connection.execute(
            """
            INSERT INTO audit_log (ts, user_id, action, result)
            VALUES (?, ?, ?, ?)
            """,
            (now, "user-a", "new.action", "success"),
        )

    subprocess.run(
        [
            sys.executable,
            str(Path("scripts") / "purge_old_audit.py"),
            "--days",
            "90",
            "--db-path",
            str(db_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    rows = read_audit_rows(db_path)
    assert [row["action"] for row in rows] == ["new.action"]
