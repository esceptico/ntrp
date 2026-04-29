"""Tool execution tests — real tool logic, controlled inputs."""

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, Field

import ntrp.tools.executor as tool_executor_module
from ntrp.agent import ToolResult
from ntrp.context.models import SessionState
from ntrp.integrations.base import Integration
from ntrp.tools.bash import bash_tool, execute_bash, is_blocked_command, is_safe_command
from ntrp.tools.core import EmptyInput, Tool, ToolCall, ToolNext, tool
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.core.types import ApprovalInfo
from ntrp.tools.discover import discover_user_tools
from ntrp.tools.executor import ToolExecutor


def _make_execution(tool_name: str = "test") -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    return ToolExecution(tool_id="t1", tool_name=tool_name, ctx=ctx)


def _register_tools(registry: ToolRegistry, tools: dict[str, Tool]) -> None:
    for name, candidate in tools.items():
        registry.register(name, candidate)


# --- Bash safety checks ---


def test_safe_commands():
    assert is_safe_command("ls")
    assert is_safe_command("git status")
    assert is_safe_command("cat file.txt")
    assert is_safe_command("python --version")
    assert not is_safe_command("rm -rf /")
    assert not is_safe_command("sudo reboot")


def test_blocked_commands():
    assert is_blocked_command("rm -rf /")
    assert is_blocked_command("rm -rf ~")
    assert is_blocked_command("dd if=/dev/zero")
    assert not is_blocked_command("ls -la")
    assert not is_blocked_command("echo hello")


# --- Bash execution ---


def test_execute_bash_simple():
    output = execute_bash("echo hello")
    assert "hello" in output


def test_execute_bash_stderr():
    output = execute_bash("echo err >&2")
    assert "err" in output
    assert "[stderr]" in output


def test_execute_bash_exit_code():
    output = execute_bash("exit 1")
    assert "[exit code: 1]" in output


def test_execute_bash_timeout():
    output = execute_bash("sleep 10", timeout=1)
    assert "timed out" in output.lower()


# --- Bash tool ---


@pytest.mark.asyncio
async def test_bash_tool_execute():
    execution = _make_execution("bash")
    result = await bash_tool.execute(execution, command="echo test123")
    assert "test123" in result.content


@pytest.mark.asyncio
async def test_bash_tool_blocked():
    execution = _make_execution("bash")
    result = await bash_tool.execute(execution, command="rm -rf /")
    assert result.is_error
    assert "Blocked" in result.content


@pytest.mark.asyncio
async def test_bash_tool_working_dir(tmp_path):
    execution = _make_execution("bash")
    result = await bash_tool.execute(execution, command="pwd", working_dir=str(tmp_path))
    assert str(tmp_path) in result.content


# --- Function tools ---


@pytest.mark.asyncio
async def test_function_tool_execute_without_args():
    async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        assert execution.tool_name == "current_time"
        return ToolResult(content="now", preview="now")

    registry = ToolRegistry()
    _register_tools(
        registry,
        {
            "current_time": tool(
                description="Get the current time.",
                execute=current_time,
            )
        },
    )

    result = await registry.execute("current_time", _make_execution("current_time"), {})

    assert result == ToolResult(content="now", preview="now")
    assert registry.get("current_time").to_dict("current_time") == {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "Get the current time.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }


class EchoInput(BaseModel):
    text: str = Field(min_length=1, description="Text to echo.")


@pytest.mark.asyncio
async def test_function_tool_execute_with_pydantic_args():
    async def echo(execution: ToolExecution, args: EchoInput) -> ToolResult:
        assert execution.tool_name == "echo"
        return ToolResult(content=f"echo: {args.text}", preview=args.text)

    registry = ToolRegistry()
    _register_tools(
        registry,
        {
            "echo": tool(
                description="Echo text.",
                input_model=EchoInput,
                execute=echo,
            )
        },
    )

    result = await registry.execute("echo", _make_execution("echo"), {"text": "hello"})

    assert result.content == "echo: hello"
    assert result.preview == "hello"
    schema = registry.get("echo").to_dict("echo")
    assert schema["function"]["parameters"]["properties"]["text"]["description"] == "Text to echo."
    assert schema["function"]["parameters"]["required"] == ["text"]


@pytest.mark.asyncio
async def test_function_tool_uses_registry_validation():
    async def echo(execution: ToolExecution, args: EchoInput) -> ToolResult:
        return ToolResult(content=args.text, preview=args.text)

    registry = ToolRegistry()
    _register_tools(
        registry,
        {
            "echo": tool(
                description="Echo text.",
                input_model=EchoInput,
                execute=echo,
            )
        },
    )

    result = await registry.execute("echo", _make_execution("echo"), {"text": ""})

    assert result.is_error
    assert result.preview == "Validation error"
    assert "Invalid arguments" in result.content


@pytest.mark.asyncio
async def test_function_tool_supports_approval_callback():
    async def approve(execution: ToolExecution, args: EchoInput) -> ApprovalInfo:
        return ApprovalInfo(description=f"Echo {args.text}", preview=args.text, diff=None)

    async def echo(execution: ToolExecution, args: EchoInput) -> ToolResult:
        return ToolResult(content=args.text, preview=args.text)

    registry = ToolRegistry()
    _register_tools(
        registry,
        {
            "echo": tool(
                description="Echo text.",
                input_model=EchoInput,
                execute=echo,
                approval=approve,
                mutates=True,
            )
        },
    )

    result = await registry.execute("echo", _make_execution("echo"), {"text": "hello"})

    assert result.preview == "Rejected"
    assert result.content == "User rejected this action and said: No UI connected — cannot approve"


@pytest.mark.asyncio
async def test_function_tool_rejects_non_tool_result_output():
    async def bad_output(execution: ToolExecution, args: EmptyInput) -> str:
        return "not a ToolResult"

    registry = ToolRegistry()
    _register_tools(
        registry,
        {
            "bad_output": tool(
                description="Return the wrong type.",
                execute=bad_output,
            )
        },
    )

    with pytest.raises(TypeError, match="function tool handlers must return ToolResult"):
        await registry.execute("bad_output", _make_execution("bad_output"), {})


def test_tool_executor_registers_integration_tool_map(monkeypatch):
    async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        return ToolResult(content="now", preview="now")

    time_tools = {
        "current_time": tool(
            description="Get the current time.",
            execute=current_time,
        )
    }
    monkeypatch.setattr(
        tool_executor_module,
        "ALL_INTEGRATIONS",
        [Integration(id="_test", label="Test", tools=time_tools)],
    )

    executor = ToolExecutor()

    assert executor.registry.get("current_time") is time_tools["current_time"]


@pytest.mark.asyncio
async def test_tool_registry_runs_middlewares_in_order():
    calls: list[str] = []

    async def middleware_one(call: ToolCall, next_call: ToolNext) -> ToolResult:
        calls.append("one:before")
        result = await next_call(call)
        calls.append("one:after")
        return result

    async def middleware_two(call: ToolCall, next_call: ToolNext) -> ToolResult:
        calls.append("two:before")
        result = await next_call(call)
        calls.append("two:after")
        return result

    async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        calls.append("execute")
        return ToolResult(content="now", preview="now")

    registry = ToolRegistry(middlewares=(middleware_one, middleware_two))
    registry.register("current_time", tool(description="Get the current time.", execute=current_time))

    result = await registry.execute("current_time", _make_execution("current_time"), {})

    assert result.content == "now"
    assert calls == ["one:before", "two:before", "execute", "two:after", "one:after"]


def test_tool_registry_rejects_duplicate_tool_names():
    async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        return ToolResult(content="now", preview="now")

    registry = ToolRegistry()
    registry.register("current_time", tool(description="Get the current time.", execute=current_time))

    with pytest.raises(ValueError, match="duplicate tool name"):
        registry.register("current_time", tool(description="Get the current time.", execute=current_time))


def test_discover_user_tools_loads_named_tool_map(tmp_path):
    (tmp_path / "custom.py").write_text(
        """
from ntrp.tools.core import EmptyInput, ToolResult, tool


async def hello(execution, args: EmptyInput) -> ToolResult:
    return ToolResult(content="hello", preview="hello")


tools = {
    "hello": tool(description="Say hello.", execute=hello),
}
""".strip()
    )

    discovered = discover_user_tools(tmp_path)

    assert set(discovered) == {"hello"}
    assert discovered["hello"].to_dict("hello")["function"]["name"] == "hello"
