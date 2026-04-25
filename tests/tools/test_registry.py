from __future__ import annotations

import pytest

from src.tools import TOOL_REGISTRY, get_tool


def test_email_tools_are_registered() -> None:
    assert {
        "read_inbox",
        "get_email",
        "send_email",
        "reply_email",
        "mark_read",
        "archive",
    }.issubset(TOOL_REGISTRY)


def test_registered_tool_has_pydantic_schemas() -> None:
    spec = get_tool("send_email")

    assert spec.name == "send_email"
    assert "properties" in spec.params_schema
    assert {"to", "subject", "body_text"}.issubset(spec.params_schema["properties"])
    assert "properties" in spec.returns_schema
    assert "status" in spec.returns_schema["properties"]


def test_get_tool_rejects_unknown_name() -> None:
    with pytest.raises(KeyError):
        get_tool("missing_tool")

