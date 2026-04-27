from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean
from typing import Any

from src.agent.loop import AgentLoop, current_agent_metrics
from src.server.inference.vllm import current_vllm_metrics
from src.server.runtime import build_chat_service
from src.server.settings import OpenModelSettings
from src.tools.registry import ToolSpec

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROMPTS = ROOT_DIR / "tests" / "fixtures" / "agent_eval_prompts.jsonl"


async def read_inbox_tool(limit: int = 5, unread_only: bool = False) -> list[dict[str, Any]]:
    messages = [
        {
            "uid": "eval-102",
            "from": "lead@example.com",
            "subject": "Launch notes",
            "date": "2026-04-19T11:00:00Z",
            "snippet": "Please confirm the launch checklist and owner.",
            "unread": False,
        },
        {
            "uid": "eval-101",
            "from": "alerts@example.com",
            "subject": "Unread billing alert",
            "date": "2026-04-19T09:00:00Z",
            "snippet": "The billing threshold was reached.",
            "unread": True,
        },
    ]
    if unread_only:
        messages = [message for message in messages if message["unread"] is True]
    return messages[:limit]


async def get_email_tool(uid: str) -> dict[str, Any]:
    return {
        "uid": uid,
        "from": "lead@example.com",
        "subject": "Launch notes",
        "date": "2026-04-19T11:00:00Z",
        "body_text": "Checklist: confirm deploy owner, rollback window, and customer note.",
        "unread": False,
    }


async def echo_tool(value: str = "") -> dict[str, str]:
    return {"echo": value}


def eval_registry() -> dict[str, ToolSpec]:
    return {
        "read_inbox": ToolSpec(
            name="read_inbox",
            description="List recent email summaries.",
            params_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "unread_only": {"type": "boolean"},
                },
            },
            returns_schema={"type": "array"},
            handler=read_inbox_tool,
        ),
        "get_email": ToolSpec(
            name="get_email",
            description="Fetch a full email by UID.",
            params_schema={
                "type": "object",
                "required": ["uid"],
                "properties": {"uid": {"type": "string"}},
            },
            returns_schema={"type": "object"},
            handler=get_email_tool,
        ),
        "echo": ToolSpec(
            name="echo",
            description="Echo a value for chat-style parse checks.",
            params_schema={"type": "object", "properties": {"value": {"type": "string"}}},
            returns_schema={"type": "object"},
            handler=echo_tool,
        ),
    }


def load_prompts(path: Path) -> list[str]:
    prompts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, str):
            prompts.append(payload)
        else:
            prompts.append(str(payload["prompt"]))
    return prompts


async def run_eval(args: argparse.Namespace) -> dict[str, float]:
    prompts = load_prompts(Path(args.prompts))
    if not prompts:
        raise SystemExit("No prompts found.")

    settings = OpenModelSettings(open_model_inference_backend=args.backend)
    runtime = build_chat_service(settings)
    loop = AgentLoop(
        runtime,
        registry=eval_registry(),
        enforce_schema=settings.open_model_agent_constrained_decoding,
    )

    parse_failures = 0
    retry_counts: list[int] = []
    first_token_latencies: list[float] = []
    total = 0

    for index in range(args.n):
        prompt = prompts[index % len(prompts)]
        result = await loop.run(prompt, user_id="eval-user", max_steps=5)
        metrics = current_agent_metrics.get()
        vllm_metrics = current_vllm_metrics.get()
        retry_counts.append(metrics.parse_retry_count if metrics else 0)
        if vllm_metrics and vllm_metrics.first_token_latency_ms is not None:
            first_token_latencies.append(vllm_metrics.first_token_latency_ms)
        if result.stopped_reason == "error" and "parse" in result.answer.lower():
            parse_failures += 1
        total += 1

    return {
        "runs": float(total),
        "parse_failure_rate": parse_failures / total if total else 0.0,
        "avg_parse_retry_count": mean(retry_counts) if retry_counts else 0.0,
        "avg_first_token_latency_ms": mean(first_token_latencies) if first_token_latencies else 0.0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure agent JSON parse reliability with local or vLLM inference.",
        epilog=(
            "Expected baseline: vLLM with constrained decoding should be below 1% parse "
            "failure; local or disabled constrained decoding commonly lands around 15-30%."
        ),
    )
    parser.add_argument("--backend", choices=["local", "vllm"], default="local")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    return parser.parse_args()


def main() -> None:
    summary = asyncio.run(run_eval(parse_args()))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
