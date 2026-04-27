from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

_TRACING_ENABLED = False
_HTTPX_INSTRUMENTED = False
_SQLALCHEMY_ENGINES: set[int] = set()


def configure_tracing(service_name: str, otlp_endpoint: str | None, sample_rate: float) -> bool:
    global _TRACING_ENABLED, _HTTPX_INSTRUMENTED
    if not otlp_endpoint:
        _TRACING_ENABLED = False
        return False
    if _TRACING_ENABLED:
        return True

    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name}),
        sampler=TraceIdRatioBased(sample_rate),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    trace.set_tracer_provider(provider)
    if not _HTTPX_INSTRUMENTED:
        HTTPXClientInstrumentor().instrument()
        _HTTPX_INSTRUMENTED = True
    _TRACING_ENABLED = True
    return True


def tracing_enabled() -> bool:
    return _TRACING_ENABLED


def instrument_fastapi(app: Any) -> None:
    if _TRACING_ENABLED:
        FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy_engine(sync_engine: Any) -> None:
    if not _TRACING_ENABLED:
        return
    engine_id = id(sync_engine)
    if engine_id in _SQLALCHEMY_ENGINES:
        return
    SQLAlchemyInstrumentor().instrument(engine=sync_engine)
    _SQLALCHEMY_ENGINES.add(engine_id)
