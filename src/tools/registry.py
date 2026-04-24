from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


ToolCallable = Callable[..., Awaitable[Any]]


class ToolSpec(BaseModel):
    name: str = Field(min_length=1)
    description: str
    params_schema: dict[str, Any]
    returns_schema: dict[str, Any]
    handler: ToolCallable

    model_config = ConfigDict(arbitrary_types_allowed=True)


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> ToolSpec:
    TOOL_REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec:
    try:
        return TOOL_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown tool: {name}") from exc
