from __future__ import annotations

import json
import sqlite3
from email.utils import format_datetime
from datetime import datetime, timezone

from src.tools import gmail_auth
from src.tools import email_tools
from src.server.settings import get_open_model_settings
from src.tools.errors import AuthError
from src.tools.gmail_auth import (
    GmailSessionToken,
    complete_gmail_oauth_flow,
    disconnect_gmail,
    get_gmail_status,
    start_gmail_oauth_flow,
    store_gmail_session_token,
)


class FakeCredentials:
    def __init__(self, *, valid: bool = True, expired: bool = False, token: str = "access-token"):
        self.token = token
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
    gmail_auth._OAUTH_STATES.clear()
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/callback")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(tmp_path / "gmail_token.json"))
    monkeypatch.setenv("OPEN_MODEL_DB_PATH", str(tmp_path / "chat.sqlite3"))
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret")


def credential_row(tmp_path, user_id: str):
    with sqlite3.connect(tmp_path / "chat.sqlite3") as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT user_id, encrypted_token, email, scopes, connected_at, updated_at
            FROM gmail_credentials
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()


def test_start_gmail_oauth_flow_stores_state_in_memory(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    monkeypatch.setattr(gmail_auth, "Flow", FakeFlow)

    url = start_gmail_oauth_flow("user-a")

    assert url.startswith("https://accounts.google.com")
    assert gmail_auth._OAUTH_STATES
    state = next(iter(gmail_auth._OAUTH_STATES))
    assert gmail_auth._OAUTH_STATES[state].user_id == "user-a"
    assert state in url


def test_complete_gmail_oauth_flow_stores_token(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    monkeypatch.setattr(gmail_auth, "Flow", FakeFlow)
    state = "known-state"
    gmail_auth._OAUTH_STATES[state] = gmail_auth.OAuthStateEntry(
        user_id="user-a", expires_at=gmail_auth._state_now() + 60
    )

    user_id = complete_gmail_oauth_flow(code="auth-code", state=state)

    row = credential_row(tmp_path, "user-a")
    assert user_id == "user-a"
    assert row is not None
    assert b"refresh-token" not in row["encrypted_token"]
    token_payload = json.loads(gmail_auth._read_encrypted_token(row["encrypted_token"]))
    assert token_payload["refresh_token"] == "refresh-token"
    assert state not in gmail_auth._OAUTH_STATES


def test_oauth_state_expires_after_ttl(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    monkeypatch.setattr(gmail_auth, "_state_now", lambda: 1000.0)
    gmail_auth._OAUTH_STATES["expired-state"] = gmail_auth.OAuthStateEntry(
        user_id="user-a", expires_at=999.0
    )

    try:
        complete_gmail_oauth_flow(code="auth-code", state="expired-state")
    except AuthError as exc:
        assert "state" in str(exc).lower()
    else:
        raise AssertionError("expired OAuth state should fail")


def test_oauth_callback_rejects_unknown_state(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)

    try:
        complete_gmail_oauth_flow(code="auth-code", state="random-state")
    except AuthError as exc:
        assert "Invalid Gmail OAuth state" in str(exc)
    else:
        raise AssertionError("unknown OAuth state should fail")


def test_status_reports_connected_account(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    store_gmail_session_token(
        GmailSessionToken(
            user_id="user-a",
            email="reader@example.com",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=None,
            scope=gmail_auth.GMAIL_READONLY_SCOPE,
            token_type="Bearer",
            client_id="client-id",
            client_secret="client-secret",
        )
    )
    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_info",
        lambda info, scopes: FakeCredentials(token=info.get("token", "access-token")),
    )
    monkeypatch.setattr(gmail_auth, "build", lambda *args, **kwargs: FakeProfileService())

    status = get_gmail_status("user-a")

    assert status.connected is True
    assert status.email == "reader@example.com"
    assert status.scopes == [gmail_auth.GMAIL_READONLY_SCOPE]


def test_loading_expired_credentials_refreshes_and_saves(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    store_gmail_session_token(
        GmailSessionToken(
            user_id="user-a",
            email="reader@example.com",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=None,
            scope=gmail_auth.GMAIL_READONLY_SCOPE,
            token_type="Bearer",
            client_id="client-id",
            client_secret="client-secret",
        )
    )
    credentials = FakeCredentials(valid=False, expired=True)
    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_info",
        lambda info, scopes: credentials,
    )

    loaded = gmail_auth.load_authorized_credentials("user-a")

    assert loaded is credentials
    row = credential_row(tmp_path, "user-a")
    token_payload = json.loads(gmail_auth._read_encrypted_token(row["encrypted_token"]))
    assert token_payload["refreshed"] is True


def test_disconnect_gmail_deletes_only_that_user(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    for user_id, email in [("user-a", "a@example.com"), ("user-b", "b@example.com")]:
        store_gmail_session_token(
            GmailSessionToken(
                user_id=user_id,
                email=email,
                access_token=f"access-{user_id}",
                refresh_token=f"refresh-{user_id}",
                expires_at=None,
                scope=gmail_auth.GMAIL_READONLY_SCOPE,
                token_type="Bearer",
                client_id="client-id",
                client_secret="client-secret",
            )
        )

    status = disconnect_gmail("user-a")

    assert status.connected is False
    assert credential_row(tmp_path, "user-a") is None
    assert credential_row(tmp_path, "user-b") is not None


def test_store_gmail_session_token_writes_user_scoped_encrypted_token(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)

    status = store_gmail_session_token(
        GmailSessionToken(
            user_id="google-user-1",
            email="reader@example.com",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=1_777_000_000,
            scope=f"openid email profile {gmail_auth.GMAIL_READONLY_SCOPE}",
            token_type="Bearer",
            client_id="client-id",
            client_secret="client-secret",
        )
    )

    row = credential_row(tmp_path, "google-user-1")
    assert status.connected is True
    assert status.email == "reader@example.com"
    assert row is not None
    assert b"refresh-token" not in row["encrypted_token"]
    token_payload = json.loads(gmail_auth._read_encrypted_token(row["encrypted_token"]))
    assert token_payload["refresh_token"] == "refresh-token"
    assert token_payload["client_secret"] == "client-secret"


def test_user_scoped_tokens_do_not_overlap(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    for user_id, email in [("google-user-1", "one@example.com"), ("google-user-2", "two@example.com")]:
        store_gmail_session_token(
            GmailSessionToken(
                user_id=user_id,
                email=email,
                access_token=f"access-{user_id}",
                refresh_token=f"refresh-{user_id}",
                expires_at=None,
                scope=gmail_auth.GMAIL_READONLY_SCOPE,
                token_type="Bearer",
                client_id="client-id",
                client_secret="client-secret",
            )
        )

    first = json.loads(
        gmail_auth._read_encrypted_token(credential_row(tmp_path, "google-user-1")["encrypted_token"])
    )
    second = json.loads(
        gmail_auth._read_encrypted_token(credential_row(tmp_path, "google-user-2")["encrypted_token"])
    )

    assert first["refresh_token"] == "refresh-google-user-1"
    assert second["refresh_token"] == "refresh-google-user-2"


def test_disconnect_only_affects_calling_user(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    for user_id, email in [("google-user-1", "one@example.com"), ("google-user-2", "two@example.com")]:
        store_gmail_session_token(
            GmailSessionToken(
                user_id=user_id,
                email=email,
                access_token=f"access-{user_id}",
                refresh_token=f"refresh-{user_id}",
                expires_at=None,
                scope=gmail_auth.GMAIL_READONLY_SCOPE,
                token_type="Bearer",
                client_id="client-id",
                client_secret="client-secret",
            )
        )
    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_info",
        lambda info, scopes: FakeCredentials(token=info.get("token", "access-token")),
    )
    monkeypatch.setattr(gmail_auth, "build", lambda *args, **kwargs: FakeProfileService())

    status = disconnect_gmail("google-user-1")

    assert status.connected is False
    assert get_gmail_status("google-user-2").connected is True


class UserMailboxService:
    def __init__(self, subject: str):
        self.subject = subject

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        return self

    def get(self, **kwargs):
        return self

    def execute(self):
        return {
            "messages": [{"id": self.subject}],
            "id": self.subject,
            "labelIds": ["INBOX"],
            "snippet": self.subject,
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "reader@example.com"},
                    {"name": "Subject", "value": self.subject},
                    {
                        "name": "Date",
                        "value": format_datetime(
                            datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
                        ),
                    },
                ]
            },
        }


async def test_user_a_inbox_does_not_leak_to_user_b(monkeypatch, tmp_path):
    configure_google_env(monkeypatch, tmp_path)
    for user_id, subject in [("user_a", "private-a"), ("user_b", "private-b")]:
        store_gmail_session_token(
            GmailSessionToken(
                user_id=user_id,
                email=f"{user_id}@example.com",
                access_token=subject,
                refresh_token=f"refresh-{user_id}",
                expires_at=None,
                scope=gmail_auth.GMAIL_READONLY_SCOPE,
                token_type="Bearer",
                client_id="client-id",
                client_secret="client-secret",
            )
        )

    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_info",
        lambda info, scopes: FakeCredentials(token=info.get("token", "access-token")),
    )
    monkeypatch.setattr(
        "src.tools.gmail_reader.build",
        lambda *args, credentials, **kwargs: UserMailboxService(credentials.token),
    )

    messages = await email_tools.read_inbox(user_id="user_b")

    assert [message.subject for message in messages] == ["private-b"]
    assert "private-a" not in [message.subject for message in messages]
