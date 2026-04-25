from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, create_model


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


def tool(name: str, description: str) -> Callable[[ToolCallable], ToolCallable]:
    def decorator(handler: ToolCallable) -> ToolCallable:
        register_tool(
            ToolSpec(
                name=name,
                description=description,
                params_schema=_params_schema(handler, name),
                returns_schema=_returns_schema(handler),
                handler=handler,
            )
        )
        return handler

    return decorator


def get_tool(name: str) -> ToolSpec:
    try:
        return TOOL_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown tool: {name}") from exc


def _params_schema(handler: ToolCallable, name: str) -> dict[str, Any]:
    signature = inspect.signature(handler)
    type_hints = get_type_hints(handler)
    fields: dict[str, tuple[Any, Any]] = {}
    for param_name, parameter in signature.parameters.items():
        annotation = type_hints.get(param_name, Any)
        default = parameter.default if parameter.default is not inspect.Signature.empty else ...
        fields[param_name] = (annotation, default)
    model = create_model(f"{name.title().replace('_', '')}Params", **fields)
    return model.model_json_schema()


def _returns_schema(handler: ToolCallable) -> dict[str, Any]:
    annotation = get_type_hints(handler).get("return")
    if annotation is None:
        return {}
    return TypeAdapter(annotation).json_schema()
