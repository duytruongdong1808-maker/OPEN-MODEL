from __future__ import annotations

import structlog
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from structlog.testing import capture_logs

from src.server.observability.logging import (
    add_otel_trace_context,
    configure_structlog,
    redact_event,
)


def test_structured_logs_merge_contextvars_and_scrub_sensitive_values() -> None:
    configure_structlog("INFO", json_output=True)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-123")

    with capture_logs(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_event,
        ]
    ) as logs:
        structlog.get_logger("test").info("password_check", password="foo", visible="bar")

    assert logs[0]["event"] == "password_check"
    assert logs[0]["password"] == "[REDACTED]"
    assert logs[0]["request_id"] == "req-123"
    assert logs[0]["visible"] == "bar"


def test_structured_logs_include_current_otel_trace_context() -> None:
    configure_structlog("INFO", json_output=True)
    span_context = SpanContext(
        trace_id=0x1234567890ABCDEF1234567890ABCDEF,
        span_id=0x1234567890ABCDEF,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state={},
    )
    span = NonRecordingSpan(span_context)

    with capture_logs(processors=[add_otel_trace_context]) as logs:
        with trace.use_span(span, end_on_exit=False):
            structlog.get_logger("test").info("span_log")

    assert logs[0]["event"] == "span_log"
    assert logs[0]["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert logs[0]["span_id"] == "1234567890abcdef"
