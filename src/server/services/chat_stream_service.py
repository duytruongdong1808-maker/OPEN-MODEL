from __future__ import annotations

import json

from fastapi import Request

from ...tools import TOOL_REGISTRY, ToolSpec
from ..services.audit_service import AuditLogger
from .email_audit_service import first_recipient_domain


def sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_steps(mode: str) -> list[tuple[str, str]]:
    if mode == "news":
        return [
            ("search", "Searching sources"),
            ("compare", "Comparing articles"),
            ("draft", "Drafting answer"),
        ]
    return [
        ("context", "Reading conversation"),
        ("draft", "Drafting answer"),
    ]


def get_web_agent_registry() -> dict[str, ToolSpec]:
    return {
        "read_inbox": TOOL_REGISTRY["read_inbox"],
        "get_email": TOOL_REGISTRY["get_email"],
    }


async def audit_agent_tool_call(
    audit: AuditLogger,
    user_id: str,
    tool_name: str,
    arguments: dict[str, object],
    request: Request,
) -> None:
    await audit.log_async(
        user_id,
        "agent.tool_call",
        target=tool_name,
        detail={"arguments_keys": sorted(str(key) for key in arguments)},
        request=request,
    )
    if tool_name == "send_email":
        recipients = arguments.get("to")
        recipient_list = recipients if isinstance(recipients, list) else []
        target = first_recipient_domain([str(recipient) for recipient in recipient_list])
        await audit.log_async(
            user_id,
            "tool.send_email",
            target=target,
            detail={
                "to_count": len(recipient_list),
                "cc_count": len(arguments.get("cc") or []),
                "bcc_count": len(arguments.get("bcc") or []),
            },
            request=request,
        )


async def inference_ready(runtime: object | None) -> bool:
    if runtime is None:
        return False
    if hasattr(runtime, "is_loaded"):
        return bool(runtime.is_loaded)
    if hasattr(runtime, "check_ready"):
        return bool(await runtime.check_ready())
    return True
