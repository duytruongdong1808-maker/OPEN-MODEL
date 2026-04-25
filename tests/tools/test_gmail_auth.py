from __future__ import annotations

import json

from src.tools import gmail_auth
from src.server.settings import get_open_model_settings
from src.tools.gmail_auth import (
    complete_gmail_oauth_flow,
    disconnect_gmail,
    get_gmail_status,
    start_gmail_oauth_flow,
)


class FakeCredentials:
    def __init__(self, *, valid: bool = True, expired: bool = False):
        self.valid = valid
        self.expired = expired
        self.refresh_token = "refresh-token"
        self.scopes = [gmail_auth.GMAIL_READONLY_SCOPE]
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        self.valid = True
        self.expired = False

    def to_json(self):
        return json.dumps(
            {
                "token": "access-token",
                "refresh_token": self.refresh_token,
                "scopes": self.scopes,
                "refreshed": self.refreshed,
            }
        )


class FakeFlow:
    credentials = FakeCredentials()

    def __init__(self, state=None):
        self.state = state
        self.redirect_uri = None
        self.fetched_code = None

    @classmethod
    def from_client_config(cls, client_config, scopes, state=None):
        assert scopes == [gmail_auth.GMAIL_READONLY_SCOPE]
        assert client_config["web"]["client_id"] == "client-id"
        return cls(state=state)

    def authorization_url(self, **kwargs):
        assert kwargs["access_type"] == "offline"
        assert kwargs["include_granted_scopes"] == "true"
        assert kwargs["prompt"] == "consent"
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={self.state}", self.state

    def fetch_token(self, *, code):
        self.fetched_code = code
        self.credentials = FakeCredentials()


class FakeProfileService:
    def users(self):
        return self

    def getProfile(self, *, userId):
        assert userId == "me"
        return self

    def execute(self):
        return {"emailAddress": "reader@example.com"}


def configure_google_env(monkeypatch, tmp_path):
    get_open_model_settings.cache_clear()
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/callback")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(tmp_path / "gmail_token.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_STATE_PATH", str(tmp_path / "gmail_state.json"))
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret")


def test_start_gmail_oauth_flow_persists_state(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    monkeypatch.setattr(gmail_auth, "Flow", FakeFlow)

    url = start_gmail_oauth_flow()

    assert url.startswith("https://accounts.google.com")
    state_payload = json.loads((tmp_path / "gmail_state.json").read_text(encoding="utf-8"))
    assert state_payload["state"]
    assert state_payload["state"] in url


def test_complete_gmail_oauth_flow_stores_token(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    monkeypatch.setattr(gmail_auth, "Flow", FakeFlow)
    state = "known-state"
    (tmp_path / "gmail_state.json").write_text(json.dumps({"state": state}), encoding="utf-8")

    complete_gmail_oauth_flow(code="auth-code", state=state)

    token_file = tmp_path / "gmail_token.json"
    assert "refresh-token" not in token_file.read_text(encoding="utf-8")
    token_payload = json.loads(gmail_auth._read_encrypted_token(token_file))
    assert token_payload["refresh_token"] == "refresh-token"
    assert not (tmp_path / "gmail_state.json").exists()


def test_status_reports_connected_account(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    gmail_auth._write_encrypted_token(tmp_path / "gmail_token.json", "{}")
    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_info",
        lambda info, scopes: FakeCredentials(),
    )
    monkeypatch.setattr(gmail_auth, "build", lambda *args, **kwargs: FakeProfileService())

    status = get_gmail_status()

    assert status.connected is True
    assert status.email == "reader@example.com"
    assert status.scopes == [gmail_auth.GMAIL_READONLY_SCOPE]


def test_loading_expired_credentials_refreshes_and_saves(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    gmail_auth._write_encrypted_token(tmp_path / "gmail_token.json", "{}")
    credentials = FakeCredentials(valid=False, expired=True)
    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_info",
        lambda info, scopes: credentials,
    )

    loaded = gmail_auth.load_authorized_credentials()

    assert loaded is credentials
    token_payload = json.loads(gmail_auth._read_encrypted_token(tmp_path / "gmail_token.json"))
    assert token_payload["refreshed"] is True


def test_disconnect_gmail_deletes_token_and_state(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    (tmp_path / "gmail_token.json").write_text("{}", encoding="utf-8")
    (tmp_path / "gmail_state.json").write_text("{}", encoding="utf-8")

    status = disconnect_gmail()

    assert status.connected is False
    assert not (tmp_path / "gmail_token.json").exists()
    assert not (tmp_path / "gmail_state.json").exists()
