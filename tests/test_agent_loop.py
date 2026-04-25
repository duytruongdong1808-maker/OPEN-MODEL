from __future__ import annotations

from collections.abc import Iterator

from src.agent.loop import AgentLoop, build_tools_prompt, parse_model_command
from src.server.runtime import GenerationStream
from src.tools.registry import ToolSpec


class ScriptedRuntime:
    def __init__(self, outputs: list[str]):
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    def stream_reply(self, *, messages, system_prompt: str, mode: str = "chat") -> GenerationStream:
        self.calls.append({"messages": messages, "system_prompt": system_prompt, "mode": mode})
        output = self.outputs.pop(0)

        def chunks() -> Iterator[str]:
            yield output

        return GenerationStream(chunks=chunks(), cancel=lambda: None)


async def echo_tool(value: str) -> dict[str, str]:
    return {"echo": value}


def echo_registry() -> dict[str, ToolSpec]:
    return {
        "echo": ToolSpec(
            name="echo",
            description="Echo a value.",
            params_schema={"type": "object", "properties": {"value": {"type": "string"}}},
            returns_schema={"type": "object"},
            handler=echo_tool,
        )
    }


def test_build_tools_prompt_includes_registered_tool() -> None:
    prompt = build_tools_prompt(echo_registry())

    assert "Available tools" in prompt
    assert "echo" in prompt


def test_parse_model_command_accepts_fenced_json() -> None:
    parsed = parse_model_command('```json\n{"final":"done"}\n```')

    assert parsed == {"final": "done"}


async def test_agent_loop_executes_tool_then_final() -> None:
    runtime = ScriptedRuntime(
        [
            '{"tool_call":{"name":"echo","arguments":{"value":"hello"}}}',
            '{"final":"I echoed hello."}',
        ]
    )
    loop = AgentLoop(runtime, registry=echo_registry())

    result = await loop.run("please echo", max_steps=3)

    assert result.stopped_reason == "final"
    assert result.answer == "I echoed hello."
    assert result.steps[1].kind == "tool"
    assert result.steps[1].result == {"echo": "hello"}
    assert runtime.calls[0]["mode"] == "agent"
    assert "Tool result for echo" in runtime.calls[1]["messages"][-1]["content"]


async def test_agent_loop_returns_parse_error() -> None:
    runtime = ScriptedRuntime(["not json", "still not json"])
    loop = AgentLoop(runtime, registry=echo_registry())

    result = await loop.run("hello")

    assert result.stopped_reason == "error"
    assert "parse error" in result.answer
    assert len(runtime.calls) == 2
