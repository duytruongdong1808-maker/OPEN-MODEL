from __future__ import annotations

import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.server.app import create_app, get_send_ledger, get_web_agent_registry
from src.server.runtime import GenerationStream
from src.server.storage import ConversationStore
from src.tools.ledger import SendLedger
from src.tools.registry import ToolSpec
from src.tools.config import get_email_settings
from src.tools.schemas import EmailMessage, EmailSummary, SendRequest, SendResult
from src.server.settings import get_open_model_settings


class FakeChatRuntime:
    def __init__(self, chunks: list[str] | None = None, error: Exception | None = None) -> None:
        self.chunks = chunks or ["Hello", " world"]
        self.error = error
        self.calls: list[dict[str, object]] = []

    def stream_reply(self, *, messages, system_prompt: str, mode: str = "chat") -> GenerationStream:
        self.calls.append({"messages": messages, "system_prompt": system_prompt, "mode": mode})

        def iterator():
            if self.error is not None:
                raise self.error
            for chunk in self.chunks:
                yield chunk

        return GenerationStream(chunks=iterator(), cancel=lambda: None)


class ScriptedAgentRuntime:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    def stream_reply(self, *, messages, system_prompt: str, mode: str = "chat") -> GenerationStream:
        self.calls.append({"messages": messages, "system_prompt": system_prompt, "mode": mode})
        output = self.outputs.pop(0)

        def iterator():
            yield output

        return GenerationStream(chunks=iterator(), cancel=lambda: None)


def parse_sse_events(payload: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    current_event: str | None = None
    current_data: str | None = None
    for line in payload.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: ") :]
        elif line.startswith("data: "):
            current_data = line[len("data: ") :]
        elif line == "" and current_event and current_data:
            events.append((current_event, json.loads(current_data)))
            current_event = None
            current_data = None
    if current_event and current_data:
        events.append((current_event, json.loads(current_data)))
    return events


def create_test_client(tmp_path: Path, runtime: FakeChatRuntime | None = None) -> TestClient:
    store = ConversationStore(tmp_path / "chat.sqlite3")
    app = create_app(store=store, runtime=runtime or FakeChatRuntime(), protect_chat_routes=False)
    return TestClient(app)


def test_create_list_and_get_conversation(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)

    create_response = client.post("/conversations")
    assert create_response.status_code == 200
    conversation = create_response.json()

    list_response = client.get("/conversations")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == conversation["id"]

    get_response = client.get(f"/conversations/{conversation['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["messages"] == []


def test_delete_conversation_removes_messages_and_returns_no_content(tmp_path: Path) -> None:
    runtime = FakeChatRuntime(chunks=["Open", " Model"])
    client = create_test_client(tmp_path, runtime=runtime)
    conversation_id = client.post("/conversations").json()["id"]

    stream_response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"message": "Keep this briefly.", "mode": "chat"},
    )
    assert stream_response.status_code == 200
    assert len(client.get(f"/conversations/{conversation_id}").json()["messages"]) == 2

    delete_response = client.delete(f"/conversations/{conversation_id}")

    assert delete_response.status_code == 204
    assert client.get(f"/conversations/{conversation_id}").status_code == 404
    assert client.get("/conversations").json() == []


def test_delete_missing_conversation_returns_not_found(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)

    response = client.delete("/conversations/missing")

    assert response.status_code == 404


def test_stream_message_persists_user_and_assistant_messages(tmp_path: Path) -> None:
    runtime = FakeChatRuntime(chunks=["Open", " Model"])
    client = create_test_client(tmp_path, runtime=runtime)
    conversation_id = client.post("/conversations").json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"message": "Tell me something useful.", "mode": "chat"},
    )
    assert response.status_code == 200

    events = parse_sse_events(response.text)
    event_names = [name for name, _ in events]
    assert event_names == [
        "message_start",
        "step_update",
        "step_update",
        "step_update",
        "assistant_delta",
        "assistant_delta",
        "step_update",
        "message_complete",
    ]

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert conversation["title"] == "Tell me something useful."
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert conversation["messages"][1]["content"] == "Open Model"
    assert runtime.calls[0]["messages"][0]["content"] == "Tell me something useful."


def test_stream_error_emits_error_event_and_does_not_persist_assistant_message(
    tmp_path: Path,
) -> None:
    runtime = FakeChatRuntime(error=RuntimeError("Generation failed."))
    client = create_test_client(tmp_path, runtime=runtime)
    conversation_id = client.post("/conversations").json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"message": "This should fail."},
    )
    assert response.status_code == 200

    events = parse_sse_events(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["message"] == "Generation failed."

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert [message["role"] for message in conversation["messages"]] == ["user"]


async def fake_read_inbox_tool(limit: int = 20, unread_only: bool = True):
    return [
        {
            "uid": "101",
            "from": "alice@example.com",
            "to": ["reader@example.com"],
            "subject": "Launch checklist",
            "date": "2026-04-18T11:00:00Z",
            "snippet": "Please review the launch checklist today.",
            "unread": True,
            "has_attachments": False,
        }
    ]


async def fake_get_email_tool(uid: str):
    return {
        "uid": uid,
        "from": "alice@example.com",
        "to": ["reader@example.com"],
        "subject": "Launch checklist",
        "date": "2026-04-18T11:00:00Z",
        "snippet": "Please review the launch checklist today.",
        "unread": True,
        "has_attachments": False,
        "body_text": "Please review the launch checklist today and send comments by 3 PM.",
    }


def fake_read_only_registry() -> dict[str, ToolSpec]:
    return {
        "read_inbox": ToolSpec(
            name="read_inbox",
            description="List recent email summaries.",
            params_schema={"type": "object"},
            returns_schema={"type": "array"},
            handler=fake_read_inbox_tool,
        ),
        "get_email": ToolSpec(
            name="get_email",
            description="Read a full email by UID.",
            params_schema={"type": "object", "properties": {"uid": {"type": "string"}}},
            returns_schema={"type": "object"},
            handler=fake_get_email_tool,
        ),
    }


def test_web_agent_registry_is_read_only() -> None:
    registry = get_web_agent_registry()

    assert set(registry) == {"read_inbox", "get_email"}
    assert "send_email" not in registry
    assert "reply_email" not in registry
    assert "archive" not in registry
    assert "mark_read" not in registry


def test_agent_mode_streams_read_only_steps_and_persists_summary(tmp_path: Path, monkeypatch) -> None:
    runtime = ScriptedAgentRuntime(
        [
            '{"tool_call":{"name":"read_inbox","arguments":{"limit":10,"unread_only":true}}}',
            '{"tool_call":{"name":"get_email","arguments":{"uid":"101"}}}',
            '{"final":"Priorities: Launch checklist. Action items: review by 3 PM."}',
        ]
    )
    monkeypatch.setattr("src.server.app.get_web_agent_registry", fake_read_only_registry)
    client = create_test_client(tmp_path, runtime=runtime)
    conversation_id = client.post("/conversations").json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"message": "Tom tat mail chua doc", "mode": "agent", "max_steps": 5},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [name for name, _ in events]
    assert event_names == [
        "message_start",
        "agent_step",
        "agent_step",
        "agent_step",
        "agent_step",
        "agent_step",
        "message_complete",
    ]
    assert events[1][1]["kind"] == "model"
    assert events[2][1]["kind"] == "tool"
    assert events[2][1]["tool_name"] == "read_inbox"
    assert events[4][1]["tool_name"] == "get_email"
    assert "read-only email summarization agent" in runtime.calls[0]["system_prompt"]

    conversation = client.get(f"/conversations/{conversation_id}").json()
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert "Launch checklist" in conversation["messages"][1]["content"]


def test_agent_mode_fallback_reports_latest_inbox_message_clearly(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = ScriptedAgentRuntime(
        [
            '{"tool_call":{"name":"read_inbox","arguments":{"limit":10,"unread_only":false}}}',
            '{"tool_call":{"name":"read_inbox","arguments":{"limit":10,"unread_only":false}}}',
        ]
    )
    monkeypatch.setattr("src.server.app.get_web_agent_registry", fake_read_only_registry)
    client = create_test_client(tmp_path, runtime=runtime)
    conversation_id = client.post("/conversations").json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"message": "đọc thư mới nhất trong hộp thư đến", "mode": "agent", "max_steps": 5},
    )

    assert response.status_code == 200
    conversation = client.get(f"/conversations/{conversation_id}").json()
    answer = conversation["messages"][1]["content"]
    assert "Hộp thư đến (INBOX)" in answer
    assert "UID: 101" in answer
    assert "Launch checklist" in answer
    assert "Mình đã đọc inbox" not in answer


def test_agent_mode_rejects_unavailable_write_tool(tmp_path: Path, monkeypatch) -> None:
    runtime = ScriptedAgentRuntime(
        [
            '{"tool_call":{"name":"send_email","arguments":{"to":["a@example.com"],"subject":"Hi","body_text":"Hello"}}}',
            '{"final":"I can only read and summarize email in this web chat."}',
        ]
    )
    monkeypatch.setattr("src.server.app.get_web_agent_registry", fake_read_only_registry)
    client = create_test_client(tmp_path, runtime=runtime)
    conversation_id = client.post("/conversations").json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"message": "Send a reply", "mode": "agent"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    tool_step = [payload for name, payload in events if name == "agent_step" and payload["kind"] == "tool"][0]
    assert tool_step["status"] == "error"
    assert "not available" in tool_step["error"]
    assert events[-1][0] == "message_complete"


def configure_tools_env(monkeypatch) -> None:
    get_email_settings.cache_clear()
    get_open_model_settings.cache_clear()
    monkeypatch.setenv("AGENT_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("AGENT_IMAP_USER", "reader@example.com")
    monkeypatch.setenv("AGENT_IMAP_PASS", "imap-secret")
    monkeypatch.setenv("AGENT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AGENT_SMTP_USER", "sender@example.com")
    monkeypatch.setenv("AGENT_SMTP_PASS", "smtp-secret")
    monkeypatch.setenv("AGENT_SMTP_FROM", "Sender <sender@example.com>")
    monkeypatch.setenv("AGENT_OPS_TOKEN", "test-token")


def tools_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_tools_inbox_endpoint_requires_bearer_token(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    client = create_test_client(tmp_path)

    response = client.get("/tools/inbox")

    assert response.status_code == 401


def test_conversations_require_bearer_token_by_default(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    app = create_app(store=ConversationStore(tmp_path / "chat.sqlite3"), runtime=FakeChatRuntime())
    client = TestClient(app)

    response = client.get("/conversations")

    assert response.status_code == 401


def test_delete_conversation_requires_bearer_token_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    configure_tools_env(monkeypatch)
    store = ConversationStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation()
    app = create_app(store=store, runtime=FakeChatRuntime())
    client = TestClient(app)

    response = client.delete(f"/conversations/{conversation.id}")

    assert response.status_code == 401
    assert store.conversation_exists(conversation.id)


def test_tools_inbox_endpoint_calls_email_tool(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    now = datetime.now(timezone.utc)

    async def fake_read_inbox(limit: int = 20, unread_only: bool = True):
        assert limit == 2
        assert unread_only is False
        return [
            EmailSummary(
                uid="123",
                **{"from": "alice@example.com"},
                to=["reader@example.com"],
                subject="Hello",
                date=now,
                snippet="Short",
                unread=True,
                has_attachments=False,
            )
        ]

    monkeypatch.setattr("src.server.app.email_tools.read_inbox", fake_read_inbox)
    client = create_test_client(tmp_path)

    response = client.get("/tools/inbox?limit=2&unread_only=false", headers=tools_headers())

    assert response.status_code == 200
    assert response.json()[0]["uid"] == "123"


def test_tools_email_endpoint_calls_email_tool(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    now = datetime.now(timezone.utc)

    async def fake_get_email(uid: str):
        assert uid == "123"
        return EmailMessage(
            uid="123",
            **{"from": "alice@example.com"},
            to=["reader@example.com"],
            subject="Hello",
            date=now,
            snippet="Short",
            unread=True,
            has_attachments=False,
            body_text="Full body",
            headers={},
            message_id="<m@example.com>",
        )

    monkeypatch.setattr("src.server.app.email_tools.get_email", fake_get_email)
    client = create_test_client(tmp_path)

    response = client.get("/tools/email/123", headers=tools_headers())

    assert response.status_code == 200
    assert response.json()["body_text"] == "Full body"


def test_tools_send_endpoint_calls_email_tool(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)

    async def fake_send_request(payload):
        assert payload.to == ["person@example.com"]
        assert payload.subject == "Dry run"
        return SendResult(status="dry_run", reason="dry-run enabled")

    monkeypatch.setattr("src.server.app.email_tools.send_request", fake_send_request)
    client = create_test_client(tmp_path)

    response = client.post(
        "/tools/send",
        headers=tools_headers(),
        json={
            "to": ["person@example.com"],
            "subject": "Dry run",
            "body_text": "Hello",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "dry_run"


def test_agent_run_endpoint_returns_final_answer(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    runtime = FakeChatRuntime(chunks=['{"final":"Inbox checked."}'])
    client = create_test_client(tmp_path, runtime=runtime)

    response = client.post(
        "/agent/run",
        headers=tools_headers(),
        json={"message": "Check my inbox", "max_steps": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Inbox checked."
    assert payload["stopped_reason"] == "final"
    assert runtime.calls[0]["mode"] == "agent"
    assert "Available tools" in runtime.calls[0]["system_prompt"]


def test_agent_run_endpoint_requires_bearer_token(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    client = create_test_client(tmp_path)

    response = client.post("/agent/run", json={"message": "hello"})

    assert response.status_code == 401


def test_gmail_auth_status_endpoint_reports_disconnected(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    monkeypatch.setattr("src.server.app.get_gmail_status", lambda: type("Status", (), {
        "connected": False,
        "email": None,
        "scopes": [],
    })())
    client = create_test_client(tmp_path)

    response = client.get("/auth/gmail/status", headers=tools_headers())

    assert response.status_code == 200
    assert response.json() == {"connected": False, "email": None, "scopes": []}


def test_gmail_login_endpoint_redirects_to_google(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    monkeypatch.setattr(
        "src.server.app.start_gmail_oauth_flow",
        lambda: "https://accounts.google.com/o/oauth2/v2/auth?state=abc",
    )
    client = create_test_client(tmp_path)

    response = client.get("/auth/gmail/login", headers=tools_headers(), follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://accounts.google.com")


def test_gmail_callback_stores_token_and_redirects_home(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    calls = []

    def fake_complete(*, code: str, state: str | None):
        calls.append((code, state))

    monkeypatch.setattr("src.server.app.complete_gmail_oauth_flow", fake_complete)
    client = create_test_client(tmp_path)

    response = client.get(
        "/auth/gmail/callback?code=auth-code&state=state-value",
        headers=tools_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert calls == [("auth-code", "state-value")]


def test_gmail_logout_endpoint_disconnects(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    monkeypatch.setattr("src.server.app.disconnect_gmail", lambda: type("Status", (), {
        "connected": False,
        "email": None,
        "scopes": [],
    })())
    client = create_test_client(tmp_path)

    response = client.post("/auth/gmail/logout", headers=tools_headers())

    assert response.status_code == 200
    assert response.json() == {"connected": False, "email": None, "scopes": []}


def test_gmail_auth_endpoints_require_bearer_token(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    client = create_test_client(tmp_path)

    response = client.get("/auth/gmail/login", follow_redirects=False)

    assert response.status_code == 401


def test_ready_check_reports_components(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    monkeypatch.setattr("src.server.app.get_gmail_status", lambda: type("Status", (), {
        "connected": False,
        "email": None,
        "scopes": [],
    })())
    client = create_test_client(tmp_path)

    response = client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["db"]["status"] == "ok"
    assert payload["checks"]["model"]["status"] == "ok"
    assert payload["checks"]["gmail"]["status"] == "not_connected"


def test_agent_approval_endpoints_update_ledger(tmp_path: Path, monkeypatch) -> None:
    configure_tools_env(monkeypatch)
    ledger = SendLedger(tmp_path / "approvals.sqlite3")
    approval_id = asyncio.run(
        ledger.create_approval(
            SendRequest(to=["person@example.com"], subject="Needs approval", body_text="Hello")
        )
    )
    app = create_app(store=ConversationStore(tmp_path / "chat.sqlite3"), runtime=FakeChatRuntime())
    app.dependency_overrides[get_send_ledger] = lambda: ledger
    client = TestClient(app)

    approve_response = client.post(
        f"/agent/approvals/{approval_id}/approve",
        headers={**tools_headers(), "X-Operator": "tester"},
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["decided_by"] == "tester"
