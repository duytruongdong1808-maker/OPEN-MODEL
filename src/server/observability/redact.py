from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_KEYS = {
    "authorization",
    "body_html",
    "body_text",
    "code",
    "cookie",
    "password",
    "secret",
    "snippet",
    "state",
    "token",
    "x-api-key",
    "x-user-id-sig",
}
SENSITIVE_KEY_SUBSTRINGS = {"password", "secret", "token"}


def is_sensitive_key(key: object) -> bool:
    key_text = str(key).lower().replace("_", "-")
    compact = key_text.replace("-", "_")
    return (
        key_text in SENSITIVE_KEYS
        or compact in SENSITIVE_KEYS
        or any(part in key_text or part in compact for part in SENSITIVE_KEY_SUBSTRINGS)
    )


def scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            scrubbed[key_text] = REDACTED if is_sensitive_key(key_text) else scrub(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return [scrub(item) for item in value]
    return value
