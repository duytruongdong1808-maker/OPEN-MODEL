from __future__ import annotations

from prometheus_client import Counter, Histogram

AGENT_RUN_DURATION_SECONDS = Histogram(
    "agent_run_duration_seconds",
    "Agent run duration in seconds.",
    ["stopped_reason", "backend"],
)
AGENT_TOOL_CALL_TOTAL = Counter(
    "agent_tool_call_total",
    "Agent tool calls by tool and status.",
    ["tool_name", "status"],
)
AGENT_PARSE_RETRY_TOTAL = Counter(
    "agent_parse_retry_total",
    "Agent parse retries by backend and reason.",
    ["backend", "reason"],
)
INFERENCE_FIRST_TOKEN_SECONDS = Histogram(
    "inference_first_token_seconds",
    "Inference first token latency in seconds.",
    ["backend", "model"],
)
INFERENCE_TOKENS_TOTAL = Counter(
    "inference_tokens_total",
    "Inference completion tokens.",
    ["backend", "model"],
)
INFERENCE_REQUEST_DURATION_SECONDS = Histogram(
    "inference_request_duration_seconds",
    "Inference request duration in seconds.",
    ["backend", "model"],
)
GMAIL_OAUTH_TOTAL = Counter(
    "gmail_oauth_total",
    "Gmail OAuth audit events.",
    ["action", "result"],
)
AUTH_LOGIN_TOTAL = Counter(
    "auth_login_total",
    "Authentication login audit events.",
    ["result"],
)


def backend_label(runtime: object) -> str:
    if getattr(runtime, "supports_constrained_decoding", False):
        return "vllm"
    return "local"
