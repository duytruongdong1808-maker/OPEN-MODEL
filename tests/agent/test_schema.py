from __future__ import annotations

import pytest
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from src.agent.schemas import build_agent_command_schema


def test_agent_command_schema_accepts_known_tool_call() -> None:
    schema = build_agent_command_schema(["read_inbox"])

    validate({"tool_call": {"name": "read_inbox", "arguments": {}}}, schema)


def test_agent_command_schema_rejects_unknown_tool_call() -> None:
    schema = build_agent_command_schema(["read_inbox"])

    with pytest.raises(ValidationError):
        validate({"tool_call": {"name": "unknown", "arguments": {}}}, schema)


def test_agent_command_schema_accepts_final_answer() -> None:
    schema = build_agent_command_schema(["read_inbox"])

    validate({"final": "hello"}, schema)


def test_agent_command_schema_rejects_extra_fields() -> None:
    schema = build_agent_command_schema(["read_inbox"])

    with pytest.raises(ValidationError):
        validate(
            {"tool_call": {"name": "read_inbox", "arguments": {}}, "extra": 1},
            schema,
        )


def test_agent_command_schema_rejects_empty_object() -> None:
    schema = build_agent_command_schema(["read_inbox"])

    with pytest.raises(ValidationError):
        validate({}, schema)
