from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from ...utils import DEFAULT_BASE_MODEL, ROOT_DIR


class OpenModelSettings(BaseSettings):
    open_model_base_model: str = DEFAULT_BASE_MODEL
    open_model_model_revision: str | None = None
    open_model_adapter_path: str | None = None
    open_model_load_in_4bit: bool | None = None
    open_model_max_new_tokens: int = Field(default=256, ge=1)
    open_model_temperature: float = Field(default=0.2, ge=0)
    open_model_top_p: float = Field(default=0.9, ge=0, le=1)
    open_model_frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    open_model_repetition_penalty: float = Field(default=1.05, gt=0)
    open_model_inference_backend: Literal["local", "vllm"] = "local"
    open_model_agent_constrained_decoding: bool = True
    open_model_vllm_url: str = "http://inference:8001/v1"
    open_model_vllm_model: str = "adapter"
    open_model_vllm_timeout_s: float = Field(default=120.0, gt=0)
    open_model_vllm_context_window: int = Field(default=1536, ge=256)
    open_model_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    open_model_database_url: str | None = None
    open_model_db_path: Path = ROOT_DIR / "outputs" / "app" / "chat.sqlite3"
    open_model_ledger_database_url: str | None = None
    open_model_ledger_db_path: Path = ROOT_DIR / "outputs" / "app" / "ledger.sqlite3"
    open_model_max_request_bytes: int = Field(default=256 * 1024, ge=1)
    open_model_log_level: str = "INFO"
    open_model_log_format: Literal["json", "console"] = "console"
    open_model_skip_model_load: bool = False
    otel_exporter_otlp_endpoint: str | None = None
    otel_traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    otel_service_name: str = "open-model-backend"
    sentry_dsn: SecretStr | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)

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

    @field_validator("otel_exporter_otlp_endpoint", mode="before")
    @classmethod
    def blank_otlp_endpoint_to_none(cls, value: object) -> object:
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
