# Observability

Open Model emits structured logs, Prometheus metrics, OpenTelemetry traces, and optional Sentry error reports.

## Local Stack

Create local secrets, then start the full stack:

```bash
cp secrets/grafana_password.example secrets/grafana_password
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Endpoints:

- Backend metrics: `http://localhost:8000/metrics` from inside the backend network, or `http://localhost:3000/api/backend/metrics` through the web proxy.
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`
- Tempo OTLP: `http://tempo:4318/v1/traces` from Compose services.

Import dashboard file:

```text
observability/grafana/dashboards/openmodel.json
```

The Compose overlay provisions Prometheus and Tempo data sources automatically.

## Backend Environment

```bash
OPEN_MODEL_LOG_FORMAT=json
OPEN_MODEL_LOG_LEVEL=INFO
OTEL_SERVICE_NAME=open-model-backend
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway.example/v1/traces
OTEL_TRACES_SAMPLE_RATE=0.1
SENTRY_DSN=https://backend-key@sentry.example/project
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

Use `OTEL_TRACES_SAMPLE_RATE=1.0` for local development when you want every trace. Leave `OTEL_EXPORTER_OTLP_ENDPOINT` empty to disable OpenTelemetry instrumentation in dev.

Common production mappings:

- Grafana Cloud or self-hosted Tempo: set `OTEL_EXPORTER_OTLP_ENDPOINT` to the OTLP HTTP traces endpoint.
- Honeycomb: set the OTLP HTTP endpoint and inject required headers at your collector or gateway.
- Datadog: send traces to the Datadog Agent or OpenTelemetry Collector and point this app at that local collector.

## Sentry

Backend Sentry is enabled only when `SENTRY_DSN` is set. Frontend browser Sentry uses `NEXT_PUBLIC_SENTRY_DSN`, which is public by design because it is bundled into browser JavaScript. Use a separate server-only DSN for `SENTRY_DSN`.

Sensitive headers and fields such as `authorization`, `cookie`, `x-user-id-sig`, `password`, `token`, `secret`, `body_text`, `body_html`, `snippet`, `code`, and `state` are scrubbed before Sentry receives events.

## Metrics

Custom metrics include:

- `agent_run_duration_seconds`
- `agent_tool_call_total`
- `agent_parse_retry_total`
- `inference_first_token_seconds`
- `inference_tokens_total`
- `inference_request_duration_seconds`
- `gmail_oauth_total`
- `auth_login_total`

FastAPI request metrics are exposed by `prometheus-fastapi-instrumentator`.

## Alerting

Alert examples are shipped in `observability/prometheus/alerts.yml` but are not auto-loaded by the local stack. Copy those rules into your Prometheus stack or Prometheus Operator setup and wire them to Alertmanager.

Threshold intent:

- `HighErrorRate`: backend 5xx rate is above 1 percent for 5 minutes.
- `SlowFirstToken`: p95 model first-token latency is above 5 seconds for 10 minutes.
- `GmailAuthFailures`: more than 10 Gmail auth failures in 10 minutes.
- `RateLimitStorm`: backend sees more than 100 HTTP 429 responses per minute.
- `AgentParseFailureSpike`: agent JSON parse retries exceed 0.05 per second for 10 minutes.
