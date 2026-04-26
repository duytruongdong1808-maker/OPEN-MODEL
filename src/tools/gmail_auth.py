from __future__ import annotations

import json
import secrets
import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .errors import AuthError, ToolError
from ..server.settings import get_open_model_settings


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = [GMAIL_READONLY_SCOPE]
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class GmailConnectionStatus:
    connected: bool
    email: str | None = None
    scopes: list[str] | None = None


@dataclass(frozen=True)
class GmailSessionToken:
    user_id: str
    email: str | None
    access_token: str
    refresh_token: str | None
    expires_at: int | None
    scope: str | None
    token_type: str | None
    client_id: str
    client_secret: str


def gmail_token_path() -> Path:
    return get_open_model_settings().google_oauth_token_path


def gmail_user_token_path(user_key: str) -> Path:
    digest = hashlib.sha256(user_key.strip().lower().encode("utf-8")).hexdigest()
    return get_open_model_settings().google_oauth_token_dir / f"{digest}.json"


def gmail_state_path() -> Path:
    return get_open_model_settings().google_oauth_state_path


def has_gmail_credentials(*, user_key: str | None = None) -> bool:
    return _resolve_token_path(user_key).exists()


def _resolve_token_path(user_key: str | None = None) -> Path:
    if user_key:
        return gmail_user_token_path(user_key)
    return gmail_token_path()


def _oauth_client_config() -> dict[str, dict[str, object]]:
    settings = get_open_model_settings()
    client_id = (settings.google_oauth_client_id or "").strip()
    client_secret = (
        settings.google_oauth_client_secret.get_secret_value()
        if settings.google_oauth_client_secret
        else ""
    ).strip()
    redirect_uri = (settings.google_oauth_redirect_uri or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise ToolError(
            "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID, "
            "GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [redirect_uri],
        }
    }


def _build_flow(*, state: str | None = None) -> Flow:
    redirect_uri = (get_open_model_settings().google_oauth_redirect_uri or "").strip()
    flow = Flow.from_client_config(_oauth_client_config(), scopes=GMAIL_SCOPES, state=state)
    flow.redirect_uri = redirect_uri
    return flow


def _token_cipher() -> Fernet:
    settings = get_open_model_settings()
    secret = None
    if settings.google_oauth_token_encryption_key:
        secret = settings.google_oauth_token_encryption_key.get_secret_value()
    elif settings.auth_secret:
        secret = settings.auth_secret.get_secret_value()
    if not secret:
        raise ToolError(
            "Set GOOGLE_OAUTH_TOKEN_ENCRYPTION_KEY or AUTH_SECRET before connecting Gmail."
        )
    try:
        if len(secret) == 44:
            return Fernet(secret.encode("ascii"))
    except Exception:
        pass
    derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(derived)


def _write_encrypted_token(path: Path, token_json: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_token_cipher().encrypt(token_json.encode("utf-8")))


def _read_encrypted_token(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return _token_cipher().decrypt(raw).decode("utf-8")
    except InvalidToken as exc:
        raise AuthError("Stored Gmail credentials could not be decrypted.") from exc


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _scopes_from_scope_string(scope: str | None) -> list[str]:
    scopes = [item for item in (scope or "").split() if item]
    return scopes or GMAIL_SCOPES


def _expiry_from_timestamp(expires_at: int | None) -> str | None:
    if not expires_at:
        return None
    return datetime.fromtimestamp(expires_at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _authorized_user_info(payload: GmailSessionToken, refresh_token: str | None) -> dict[str, object]:
    info: dict[str, object] = {
        "token": payload.access_token,
        "refresh_token": refresh_token,
        "token_uri": GOOGLE_TOKEN_URI,
        "client_id": payload.client_id,
        "client_secret": payload.client_secret,
        "scopes": _scopes_from_scope_string(payload.scope),
        "email": payload.email,
        "token_type": payload.token_type,
    }
    expiry = _expiry_from_timestamp(payload.expires_at)
    if expiry:
        info["expiry"] = expiry
    return {key: value for key, value in info.items() if value is not None}


def store_gmail_session_token(payload: GmailSessionToken) -> GmailConnectionStatus:
    if not payload.user_id.strip():
        raise AuthError("Google user identity is missing.")
    if not payload.access_token.strip():
        raise AuthError("Google access token is missing.")
    if GMAIL_READONLY_SCOPE not in _scopes_from_scope_string(payload.scope):
        raise AuthError("Google sign-in did not grant Gmail read-only access.")

    token_path = gmail_user_token_path(payload.user_id)
    refresh_token = payload.refresh_token
    if not refresh_token and token_path.exists():
        try:
            existing = json.loads(_read_encrypted_token(token_path))
            refresh_token = existing.get("refresh_token") or None
        except Exception:
            refresh_token = None
    if not refresh_token:
        raise AuthError("Google did not return a refresh token. Sign in with Google again.")

    _write_encrypted_token(
        token_path,
        json.dumps(_authorized_user_info(payload, refresh_token), ensure_ascii=False),
    )
    return GmailConnectionStatus(
        connected=True,
        email=payload.email,
        scopes=_scopes_from_scope_string(payload.scope),
    )


def start_gmail_oauth_flow() -> str:
    state = secrets.token_urlsafe(32)
    flow = _build_flow(state=state)
    authorization_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _write_json(gmail_state_path(), {"state": returned_state or state})
    return authorization_url


def complete_gmail_oauth_flow(*, code: str, state: str | None) -> None:
    state_path = gmail_state_path()
    if not state_path.exists():
        raise AuthError("Missing Gmail OAuth state. Start sign-in again.")
    expected_state = str(_read_json(state_path).get("state", ""))
    if not state or not secrets.compare_digest(state, expected_state):
        raise AuthError("Invalid Gmail OAuth state. Start sign-in again.")

    flow = _build_flow(state=state)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise AuthError("Gmail OAuth token exchange failed.") from exc

    credentials = flow.credentials
    _write_encrypted_token(gmail_token_path(), credentials.to_json())
    state_path.unlink(missing_ok=True)


def load_authorized_credentials(*, user_key: str | None = None) -> Credentials:
    token_path = _resolve_token_path(user_key)
    if not token_path.exists():
        raise AuthError("Gmail is not connected. Sign in with Google to let the agent read mail.")

    try:
        credentials = Credentials.from_authorized_user_info(
            json.loads(_read_encrypted_token(token_path)), GMAIL_SCOPES
        )
    except Exception as exc:
        raise AuthError("Stored Gmail credentials could not be loaded.") from exc

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleAuthRequest())
        except (RefreshError, GoogleAuthError) as exc:
            raise AuthError("Gmail authorization expired. Sign in again.") from exc
        _write_encrypted_token(token_path, credentials.to_json())

    if not credentials.valid:
        raise AuthError("Gmail authorization is invalid. Sign in again.")
    return credentials


def get_gmail_status(*, user_key: str | None = None) -> GmailConnectionStatus:
    if not has_gmail_credentials(user_key=user_key):
        return GmailConnectionStatus(connected=False, scopes=[])
    try:
        credentials = load_authorized_credentials(user_key=user_key)
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        return GmailConnectionStatus(
            connected=True,
            email=profile.get("emailAddress"),
            scopes=list(credentials.scopes or GMAIL_SCOPES),
        )
    except Exception:
        return GmailConnectionStatus(connected=False, scopes=[])


def disconnect_gmail() -> GmailConnectionStatus:
    gmail_token_path().unlink(missing_ok=True)
    gmail_state_path().unlink(missing_ok=True)
    return GmailConnectionStatus(connected=False, scopes=[])


def disconnect_gmail_user(user_key: str | None) -> GmailConnectionStatus:
    if user_key:
        gmail_user_token_path(user_key).unlink(missing_ok=True)
    return GmailConnectionStatus(connected=False, scopes=[])
