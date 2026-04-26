from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import sqlite3
import time
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
from ..server.storage import utcnow_iso


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = [GMAIL_READONLY_SCOPE]
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
OAUTH_STATE_TTL_SECONDS = 10 * 60
LEGACY_TOKEN_WARNING = (
    "Legacy gmail_token.json detected — Gmail is now per-user. Ask each user to reconnect Gmail. "
    "The legacy file will be ignored."
)

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class OAuthStateEntry:
    user_id: str
    expires_at: float


# OAuth state is intentionally process-local. In multi-instance deployments, the OAuth callback
# must route back to the same instance that created the state token, for example via sticky sessions.
_OAUTH_STATES: dict[str, OAuthStateEntry] = {}


def legacy_gmail_token_path() -> Path:
    return get_open_model_settings().google_oauth_token_path


def warn_if_legacy_token_file_exists() -> None:
    if legacy_gmail_token_path().exists():
        logger.warning(LEGACY_TOKEN_WARNING)


def _db_path() -> Path:
    db_path = Path(get_open_model_settings().open_model_db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_gmail_credentials_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_credentials (
            user_id TEXT PRIMARY KEY,
            encrypted_token BLOB NOT NULL,
            email TEXT,
            scopes TEXT,
            connected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


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


def _encrypt_token(token_json: str) -> bytes:
    return _token_cipher().encrypt(token_json.encode("utf-8"))


def _decrypt_token(raw: bytes) -> str:
    try:
        return _token_cipher().decrypt(raw).decode("utf-8")
    except InvalidToken as exc:
        raise AuthError("Stored Gmail credentials could not be decrypted.") from exc


def _read_encrypted_token(raw: bytes | Path) -> str:
    if isinstance(raw, Path):
        raw = raw.read_bytes()
    return _decrypt_token(raw)


def _scopes_from_scope_string(scope: str | None) -> list[str]:
    scopes = [item for item in (scope or "").split() if item]
    return scopes or GMAIL_SCOPES


def _scope_json(scopes: list[str]) -> str:
    return json.dumps(scopes, ensure_ascii=False)


def _parse_scope_json(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        scopes = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(scopes, list):
        return []
    return [str(scope) for scope in scopes if str(scope)]


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


def _load_credential_row(user_id: str) -> sqlite3.Row | None:
    with _connect() as connection:
        _ensure_gmail_credentials_table(connection)
        return connection.execute(
            """
            SELECT user_id, encrypted_token, email, scopes, connected_at, updated_at
            FROM gmail_credentials
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()


def _store_token_row(
    user_id: str,
    token_json: str,
    *,
    email: str | None = None,
    scopes: list[str] | None = None,
) -> None:
    timestamp = utcnow_iso()
    encrypted_token = _encrypt_token(token_json)
    with _connect() as connection:
        _ensure_gmail_credentials_table(connection)
        existing = connection.execute(
            "SELECT connected_at FROM gmail_credentials WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        connected_at = existing["connected_at"] if existing is not None else timestamp
        connection.execute(
            """
            INSERT INTO gmail_credentials (
                user_id,
                encrypted_token,
                email,
                scopes,
                connected_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                encrypted_token = excluded.encrypted_token,
                email = excluded.email,
                scopes = excluded.scopes,
                updated_at = excluded.updated_at
            """,
            (user_id, encrypted_token, email, _scope_json(scopes or []), connected_at, timestamp),
        )


def has_gmail_credentials(user_id: str) -> bool:
    user_id = user_id.strip()
    if not user_id:
        return False
    return _load_credential_row(user_id) is not None


def _prune_oauth_states(now: float | None = None) -> None:
    now = _state_now() if now is None else now
    expired = [state for state, entry in _OAUTH_STATES.items() if entry.expires_at <= now]
    for state in expired:
        _OAUTH_STATES.pop(state, None)


def _state_now() -> float:
    return time.time()


def _consume_oauth_state(state: str | None) -> str:
    if not state:
        raise AuthError("Invalid Gmail OAuth state. Start sign-in again.")
    now = _state_now()
    _prune_oauth_states(now)
    entry = _OAUTH_STATES.pop(state, None)
    if entry is None:
        raise AuthError("Invalid Gmail OAuth state. Start sign-in again.")
    if entry.expires_at <= now:
        raise AuthError("Gmail OAuth state expired. Start sign-in again.")
    return entry.user_id


def store_gmail_session_token(payload: GmailSessionToken) -> GmailConnectionStatus:
    user_id = payload.user_id.strip()
    if not user_id:
        raise AuthError("Google user identity is missing.")
    if not payload.access_token.strip():
        raise AuthError("Google access token is missing.")
    scopes = _scopes_from_scope_string(payload.scope)
    if GMAIL_READONLY_SCOPE not in scopes:
        raise AuthError("Google sign-in did not grant Gmail read-only access.")

    refresh_token = payload.refresh_token
    if not refresh_token:
        existing = _load_credential_row(user_id)
        if existing is not None:
            try:
                existing_payload = json.loads(_decrypt_token(existing["encrypted_token"]))
                refresh_token = existing_payload.get("refresh_token") or None
            except Exception:
                refresh_token = None
    if not refresh_token:
        raise AuthError("Google did not return a refresh token. Sign in with Google again.")

    _store_token_row(
        user_id,
        json.dumps(_authorized_user_info(payload, refresh_token), ensure_ascii=False),
        email=payload.email,
        scopes=scopes,
    )
    return GmailConnectionStatus(connected=True, email=payload.email, scopes=scopes)


def start_gmail_oauth_flow(user_id: str) -> str:
    user_id = user_id.strip()
    if not user_id:
        raise AuthError("Google user identity is missing.")
    state = secrets.token_urlsafe(32)
    _prune_oauth_states()
    _OAUTH_STATES[state] = OAuthStateEntry(
        user_id=user_id, expires_at=_state_now() + OAUTH_STATE_TTL_SECONDS
    )
    flow = _build_flow(state=state)
    authorization_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    if returned_state and returned_state != state:
        entry = _OAUTH_STATES.pop(state)
        _OAUTH_STATES[returned_state] = entry
    return authorization_url


def complete_gmail_oauth_flow(code: str, state: str) -> str:
    user_id = _consume_oauth_state(state)
    flow = _build_flow(state=state)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise AuthError("Gmail OAuth token exchange failed.") from exc

    credentials = flow.credentials
    token_payload = json.loads(credentials.to_json())
    scopes = [str(scope) for scope in token_payload.get("scopes") or GMAIL_SCOPES]
    _store_token_row(
        user_id,
        credentials.to_json(),
        email=token_payload.get("email"),
        scopes=scopes,
    )
    return user_id


def load_authorized_credentials(user_id: str) -> Credentials:
    row = _load_credential_row(user_id)
    if row is None:
        raise AuthError("Gmail is not connected. Sign in with Google to let the agent read mail.")

    try:
        token_payload = json.loads(_decrypt_token(row["encrypted_token"]))
        credentials = Credentials.from_authorized_user_info(token_payload, GMAIL_SCOPES)
    except Exception as exc:
        raise AuthError("Stored Gmail credentials could not be loaded.") from exc

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleAuthRequest())
        except (RefreshError, GoogleAuthError) as exc:
            raise AuthError("Gmail authorization expired. Sign in again.") from exc
        _store_token_row(
            user_id,
            credentials.to_json(),
            email=row["email"],
            scopes=list(credentials.scopes or _parse_scope_json(row["scopes"]) or GMAIL_SCOPES),
        )

    if not credentials.valid:
        raise AuthError("Gmail authorization is invalid. Sign in again.")
    return credentials


def get_gmail_status(user_id: str) -> GmailConnectionStatus:
    row = _load_credential_row(user_id)
    if row is None:
        return GmailConnectionStatus(connected=False, scopes=[])
    try:
        credentials = load_authorized_credentials(user_id)
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress") or row["email"]
        scopes = list(credentials.scopes or _parse_scope_json(row["scopes"]) or GMAIL_SCOPES)
        return GmailConnectionStatus(connected=True, email=email, scopes=scopes)
    except Exception:
        return GmailConnectionStatus(connected=False, scopes=[])


def disconnect_gmail(user_id: str) -> GmailConnectionStatus:
    with _connect() as connection:
        _ensure_gmail_credentials_table(connection)
        connection.execute("DELETE FROM gmail_credentials WHERE user_id = ?", (user_id,))
    return GmailConnectionStatus(connected=False, scopes=[])
