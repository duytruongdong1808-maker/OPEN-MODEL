from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

from ..core.config import OpenModelSettings
from .redact import REDACTED, is_sensitive_key, scrub


def _scrub_headers(headers: Any) -> Any:
    if not isinstance(headers, dict):
        return headers
    return {
        str(key): REDACTED if is_sensitive_key(key) else value for key, value in headers.items()
    }


def before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        request["headers"] = _scrub_headers(request.get("headers"))
        if "cookies" in request:
            request["cookies"] = REDACTED

    for key in ("extra", "contexts"):
        if key in event:
            event[key] = scrub(event[key])

    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict) and isinstance(breadcrumbs.get("values"), list):
        breadcrumbs["values"] = [scrub(item) for item in breadcrumbs["values"]]
    return event


def init_sentry(settings: OpenModelSettings) -> None:
    if settings.sentry_dsn is None:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=before_send,
        integrations=[FastApiIntegration()],
    )
