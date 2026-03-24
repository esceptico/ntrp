"""Tool execution tests — real tool logic, controlled inputs."""

from datetime import UTC, datetime

import pytest

from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.tools.bash import BashTool, execute_bash, is_blocked_command, is_safe_command
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry


def _make_execution(tool_name: str = "test") -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        channel=Channel(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    return ToolExecution(tool_id="t1", tool_name=tool_name, ctx=ctx)


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
    tool = BashTool()
    execution = _make_execution("bash")
    result = await tool.execute(execution, command="echo test123")
    assert "test123" in result.content


@pytest.mark.asyncio
async def test_bash_tool_blocked():
    tool = BashTool()
    execution = _make_execution("bash")
    result = await tool.execute(execution, command="rm -rf /")
    assert result.is_error
    assert "Blocked" in result.content


@pytest.mark.asyncio
async def test_bash_tool_working_dir(tmp_path):
    tool = BashTool()
    execution = _make_execution("bash")
    result = await tool.execute(execution, command="pwd", working_dir=str(tmp_path))
    assert str(tmp_path) in result.content
