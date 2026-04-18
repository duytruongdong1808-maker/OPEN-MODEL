from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.server.app import create_app
from src.server.runtime import GenerationStream
from src.server.storage import ConversationStore


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
    app = create_app(store=store, runtime=runtime or FakeChatRuntime())
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


def test_stream_error_emits_error_event_and_does_not_persist_assistant_message(tmp_path: Path) -> None:
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
