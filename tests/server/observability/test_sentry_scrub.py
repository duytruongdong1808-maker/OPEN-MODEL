from __future__ import annotations

from src.server.observability.sentry import before_send


def test_sentry_before_send_scrubs_sensitive_headers_and_context() -> None:
    event = {
        "request": {
            "headers": {
                "authorization": "Bearer secret",
                "x-user-id-sig": "sig",
                "x-api-key": "key",
                "cookie": "session=value",
                "user-agent": "pytest",
            },
            "cookies": {"session": "value"},
        },
        "extra": {
            "password": "foo",
            "nested": {"body_text": "private", "safe": "ok"},
        },
        "contexts": {"trace": {"token": "abc"}},
        "breadcrumbs": {"values": [{"data": {"secret": "abc", "safe": "ok"}}]},
    }

    scrubbed = before_send(event, {})

    assert scrubbed["request"]["headers"]["authorization"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["x-user-id-sig"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["x-api-key"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["cookie"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["user-agent"] == "pytest"
    assert scrubbed["request"]["cookies"] == "[REDACTED]"
    assert scrubbed["extra"]["password"] == "[REDACTED]"
    assert scrubbed["extra"]["nested"]["body_text"] == "[REDACTED]"
    assert scrubbed["contexts"]["trace"]["token"] == "[REDACTED]"
    assert scrubbed["breadcrumbs"]["values"][0]["data"]["secret"] == "[REDACTED]"
