from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from ..utils import DEFAULT_BASE_MODEL, ROOT_DIR


class OpenModelSettings(BaseSettings):
    open_model_base_model: str = DEFAULT_BASE_MODEL
    open_model_model_revision: str | None = None
    open_model_adapter_path: str | None = None
    open_model_load_in_4bit: bool | None = None
    open_model_max_new_tokens: int = Field(default=256, ge=1)
    open_model_temperature: float = Field(default=0.2, ge=0)
    open_model_top_p: float = Field(default=0.9, ge=0, le=1)
    open_model_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    open_model_database_url: str | None = None
    open_model_db_path: Path = ROOT_DIR / "outputs" / "app" / "chat.sqlite3"
    open_model_ledger_database_url: str | None = None
    open_model_ledger_db_path: Path = ROOT_DIR / "outputs" / "app" / "ledger.sqlite3"
    open_model_max_request_bytes: int = Field(default=256 * 1024, ge=1)
    open_model_log_level: str = "INFO"
    open_model_skip_model_load: bool = False

    agent_ops_token: SecretStr | None = None

    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    google_oauth_redirect_uri: str | None = None
    google_oauth_token_path: Path = ROOT_DIR / "outputs" / "app" / "gmail_token.json"
    google_oauth_token_encryption_key: SecretStr | None = None

    auth_secret: SecretStr | None = None
    internal_hmac_secret: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("open_model_cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("open_model_database_url", mode="before")
    @classmethod
    def blank_database_url_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("open_model_ledger_database_url", mode="before")
    @classmethod
    def blank_ledger_database_url_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("internal_hmac_secret")
    @classmethod
    def validate_internal_hmac_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        secret = value.get_secret_value()
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("INTERNAL_HMAC_SECRET must be at least 32 bytes.")
        return value


@lru_cache
def get_open_model_settings() -> OpenModelSettings:
    return OpenModelSettings()
