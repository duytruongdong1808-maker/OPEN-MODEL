from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.server.app import create_app
from src.server.settings import get_open_model_settings
from src.server.storage import ConversationStore


def test_metrics_endpoint_exposes_custom_and_incremented_metrics(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGENT_OPS_TOKEN", "test-token")
    get_open_model_settings.cache_clear()
    app = create_app(
        store=ConversationStore(tmp_path / "chat.sqlite3"),
        runtime=None,
        protect_chat_routes=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/audit/login",
            headers={"Authorization": "Bearer test-token"},
            json={"user_id": "user-a", "result": "success", "provider": "credentials"},
        )
        assert response.status_code == 200

        metrics = client.get("/metrics").text

    assert "# HELP agent_run_duration_seconds" in metrics
    assert 'auth_login_total{result="success"}' in metrics
