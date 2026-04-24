from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from email.utils import parseaddr

from pydantic import EmailStr, Field, SecretStr, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class EmailSettings(BaseSettings):
    imap_host: str
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_user: str
    imap_pass: SecretStr
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    archive_mailbox: str = "Archive"

    smtp_host: str
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str
    smtp_pass: SecretStr
    smtp_starttls: bool = True
    smtp_from: str

    dry_run: bool = True
    allowed_recipient_domains: Annotated[list[str], NoDecode] = Field(default_factory=list)
    daily_send_cap: int = Field(default=20, ge=1)
    require_approval: bool = True
    max_fetch_batch: int = Field(default=50, ge=1, le=500)
    ops_token: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENT_", extra="ignore")

    @field_validator("allowed_recipient_domains", mode="before")
    @classmethod
    def split_domains(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [part for part in value.replace(",", " ").split() if part]
        return value

    @field_validator("allowed_recipient_domains")
    @classmethod
    def normalize_allowed_domains(cls, value: list[str]) -> list[str]:
        return [domain.strip().lower().removeprefix("@") for domain in value if domain.strip()]

    @field_validator("smtp_from")
    @classmethod
    def validate_smtp_from(cls, value: str) -> str:
        _, address = parseaddr(value)
        TypeAdapter(EmailStr).validate_python(address)
        return value


@lru_cache
def get_email_settings() -> EmailSettings:
    return EmailSettings()
