from __future__ import annotations

from pathlib import Path

import structlog
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from src.server.app import create_app
from src.server.settings import get_open_model_settings
from src.server.storage import ConversationStore


def test_request_id_header_and_access_log_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MODEL_LOG_FORMAT", "json")
    get_open_model_settings.cache_clear()
    app = create_app(
        store=ConversationStore(tmp_path / "chat.sqlite3"),
        runtime=None,
        protect_chat_routes=False,
    )

    with capture_logs(
        processors=[
            structlog.contextvars.merge_contextvars,
        ]
    ) as logs:
        with TestClient(app) as client:
            response = client.get("/health/live")

    request_id = response.headers["x-request-id"]
    access_log = next(log for log in logs if log["event"] == "http.request")

    assert request_id
    assert access_log["request_id"] == request_id
    assert access_log["method"] == "GET"
    assert access_log["path"] == "/health/live"
    assert access_log["status"] == 200
