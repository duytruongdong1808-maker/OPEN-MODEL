from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1)
    system_prompt: str | None = None
    max_steps: int = Field(default=5, ge=1, le=10)


class AgentStep(BaseModel):
    index: int
    kind: Literal["model", "tool"]
    status: Literal["ok", "error"]
    content: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    result: Any | None = None
    error: str | None = None


class AgentRunResult(BaseModel):
    answer: str
    steps: list[AgentStep] = Field(default_factory=list)
    stopped_reason: Literal["final", "max_steps", "error"]


class ApprovalDecisionResult(BaseModel):
    id: str
    status: Literal["approved", "rejected", "expired", "pending"]
    decided_at: str | None = None
    decided_by: str | None = None


def build_agent_command_schema(tool_names: list[str]) -> dict[str, Any]:
    """JSON schema enforcing either {tool_call:{name,arguments}} or {final:str}."""
    return {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "required": ["tool_call"],
                "additionalProperties": False,
                "properties": {
                    "tool_call": {
                        "type": "object",
                        "required": ["name", "arguments"],
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string", "enum": tool_names},
                            "arguments": {"type": "object"},
                        },
                    }
                },
            },
            {
                "type": "object",
                "required": ["final"],
                "additionalProperties": False,
                "properties": {"final": {"type": "string"}},
            },
        ],
    }
