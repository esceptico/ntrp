"""Tool execution tests — real tool logic, controlled inputs."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

import ntrp.database as database
import ntrp.tools.executor as tool_executor_module
from ntrp.agent import ToolResult
from ntrp.constants import OFFLOAD_PREVIEW_CHARS, OFFLOAD_THRESHOLD
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore
from ntrp.core.tool_executor import NtrpToolExecutor
from ntrp.integrations.base import Integration
from ntrp.tools.bash import bash_tool, execute_bash, is_blocked_command, is_safe_command
from ntrp.tools.core import EmptyInput, Tool, ToolCall, ToolNext, tool
from ntrp.tools.core.context import (
    ApprovalControls,
    BackgroundTaskRegistry,
    IOBridge,
    RunContext,
    ToolContext,
    ToolExecution,
)
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.core.types import ApprovalInfo, ToolAction, ToolOverrideDecision, ToolPolicy, ToolScope
from ntrp.tools.discover import discover_user_tools
from ntrp.tools.executor import ToolExecutor
from ntrp.tools.todos import update_todos_tool

READ_INTERNAL_POLICY = ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL)
WRITE_INTERNAL_APPROVAL_POLICY = ToolPolicy(
    action=ToolAction.WRITE,
    scope=ToolScope.INTERNAL,
    requires_approval=True,
)


def test_tool_policy_model_defaults():
    policy = ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL)

    assert policy.action == ToolAction.READ
    assert policy.scope == ToolScope.INTERNAL
    assert policy.requires_approval is False
    assert policy.permissions == frozenset()
    assert policy.timeout_seconds is None
    assert policy.audit is True
    assert policy.max_result_chars is None
    assert policy.offload is True


def test_function_tool_metadata_exposes_policy():
    async def handler(execution, args):
        return ToolResult(content="ok")

    t = tool(
        description="Reads internal state.",
        execute=handler,
        policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    )

    metadata = t.get_metadata("read_state")

    assert metadata["policy"] == {
        "action": "read",
        "scope": "internal",
        "requires_approval": False,
        "permissions": [],
        "timeout_seconds": None,
        "audit": True,
        "max_result_chars": None,
        "offload": True,
    }


def test_all_registered_tools_have_policy():
    executor = ToolExecutor()
    for name, tool_obj in executor.registry.tools.items():
        assert isinstance(tool_obj.policy, ToolPolicy), name


def test_tool_overrides_hide_deny_and_patch_approval_policy():
    async def handler(execution, args):
        return ToolResult(content="ok")

    registry = ToolRegistry(
        tool_overrides={
            "read_state": ToolOverrideDecision.ASK,
            "write_state": ToolOverrideDecision.APPROVE,
            "blocked": ToolOverrideDecision.DENY,
        }
    )
    _register_tools(
        registry,
        {
            "read_state": tool(
                description="Read state.",
                execute=handler,
                policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
            ),
            "write_state": tool(
                description="Write state.",
                execute=handler,
                policy=ToolPolicy(
                    action=ToolAction.WRITE,
                    scope=ToolScope.INTERNAL,
                    requires_approval=True,
                ),
            ),
            "blocked": tool(
                description="Blocked.",
                execute=handler,
                policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
            ),
        },
    )

    schemas = registry.get_schemas()
    names = {s["function"]["name"] for s in schemas}
    metadata = {item["name"]: item for item in registry.get_metadata()}

    assert names == {"read_state", "write_state"}
    assert metadata["read_state"]["policy"]["requires_approval"] is True
    assert metadata["read_state"]["override"] == "ask"
    assert metadata["write_state"]["policy"]["requires_approval"] is False
    assert metadata["write_state"]["override"] == "approve"
    assert metadata["blocked"]["override"] == "deny"


@pytest.mark.asyncio
async def test_tool_override_deny_blocks_execution():
    async def handler(execution, args):
        return ToolResult(content="should not run")

    registry = ToolRegistry(tool_overrides={"blocked": ToolOverrideDecision.DENY})
    _register_tools(
        registry,
        {
            "blocked": tool(
                description="Blocked.",
                execute=handler,
                policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
            )
        },
    )

    result = await registry.execute("blocked", _make_execution("blocked"), {})

    assert result.is_error is True
    assert result.preview == "Denied by settings"


@pytest.mark.asyncio
async def test_tool_override_ask_bypasses_run_auto_approve():
    async def handler(execution, args):
        return ToolResult(content="ok")

    registry = ToolRegistry(tool_overrides={"read_state": ToolOverrideDecision.ASK})
    _register_tools(
        registry,
        {
            "read_state": tool(
                description="Read state.",
                execute=handler,
                policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
            )
        },
    )
    session_state = SessionState(session_id="test", started_at=datetime.now(UTC))
    ctx = ToolContext(
        session_state=session_state,
        registry=registry,
        run=RunContext(run_id="run-1", approval_controls=ApprovalControls(skip_approvals=True)),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )

    rejection = await ToolExecution(tool_id="call-1", tool_name="read_state", ctx=ctx).request_approval("Approve")

    assert rejection is not None
    assert rejection.feedback == "No UI connected — cannot approve"


def _make_execution(tool_name: str = "test") -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    return ToolExecution(tool_id="t1", tool_name=tool_name, ctx=ctx)


def _make_tool_context(registry: ToolRegistry, session_id: str = "test") -> ToolContext:
    return ToolContext(
        session_state=SessionState(session_id=session_id, started_at=datetime.now(UTC)),
        registry=registry,
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id=session_id),
    )


@pytest_asyncio.fixture
async def session_store(tmp_path: Path):
    conn = await database.connect(tmp_path / "sessions.db")
    read_conn = await database.connect(tmp_path / "sessions.db", readonly=True)
    store = SessionStore(conn, read_conn)
    await store.init_schema()
    yield store
    await read_conn.close()
    await conn.close()


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


@pytest.mark.asyncio
async def test_update_todos_tool_emits_todo_event():
    emitted = []

    async def emit(event):
        emitted.append(event)

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(emit=emit),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    execution = ToolExecution(tool_id="call-todos", tool_name="update_todos", ctx=ctx)

    result = await update_todos_tool.execute(
        execution,
        explanation="Track the rollout.",
        items=[
            {"content": "Research prior art", "status": "completed"},
            {"content": "Implement server tool", "status": "in_progress"},
            {"content": "Polish desktop UI", "status": "pending"},
        ],
    )

    assert result.preview == "1/3 done"
    assert result.data == {
        "items": [
            {"content": "Research prior art", "status": "completed"},
            {"content": "Implement server tool", "status": "in_progress"},
            {"content": "Polish desktop UI", "status": "pending"},
        ],
        "explanation": "Track the rollout.",
    }
    assert [event.type.value for event in emitted] == ["todo_updated"]
    assert emitted[0].run_id == "run-1"
    assert emitted[0].tool_call_id == "call-todos"


@pytest.mark.asyncio
async def test_update_todos_rejects_multiple_in_progress_items():
    registry = ToolRegistry()
    _register_tools(registry, {"update_todos": update_todos_tool})

    result = await registry.execute(
        "update_todos",
        _make_execution("update_todos"),
        {
            "items": [
                {"content": "First", "status": "in_progress"},
                {"content": "Second", "status": "in_progress"},
            ],
        },
    )

    assert result.is_error
    assert result.preview == "Validation error"


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
                policy=READ_INTERNAL_POLICY,
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
                policy=READ_INTERNAL_POLICY,
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
                policy=READ_INTERNAL_POLICY,
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
                policy=WRITE_INTERNAL_APPROVAL_POLICY,
            )
        },
    )

    result = await registry.execute("echo", _make_execution("echo"), {"text": "hello"})

    assert result.preview == "Rejected"
    assert result.content == "User rejected this action and said: No UI connected — cannot approve"


@pytest.mark.asyncio
async def test_function_tool_requires_approval_without_preview_callback():
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
                policy=WRITE_INTERNAL_APPROVAL_POLICY,
            )
        },
    )

    result = await registry.execute("echo", _make_execution("echo"), {"text": "hello"})

    assert result.preview == "Rejected"
    assert result.content == "User rejected this action and said: No UI connected — cannot approve"


@pytest.mark.asyncio
async def test_tool_approval_timeout_expires_pending_request():
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
                policy=WRITE_INTERNAL_APPROVAL_POLICY,
            )
        },
    )
    emitted = []
    recorded = []
    resolved = []
    pending: dict[str, asyncio.Future] = {}

    async def emit(event):
        emitted.append(event)

    async def record_approval(**kwargs):
        recorded.append(kwargs)

    async def resolve_approval(**kwargs):
        resolved.append(kwargs)

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=registry,
        run=RunContext(run_id="run-1"),
        io=IOBridge(
            emit=emit,
            pending_approvals=pending,
            record_approval=record_approval,
            resolve_approval=resolve_approval,
            approval_timeout_seconds=0.001,
        ),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    execution = ToolExecution(tool_id="call-1", tool_name="echo", ctx=ctx)

    rejection = await execution.request_approval("Echo hello", preview="hello")

    assert rejection is not None
    assert rejection.feedback == "Approval timed out"
    assert pending == {}
    assert len(emitted) == 1
    assert recorded[0]["action"] == "write"
    assert recorded[0]["scope"] == "internal"
    assert recorded[0]["expires_at"] is not None
    assert resolved == [
        {
            "run_id": "run-1",
            "tool_call_id": "call-1",
            "status": "expired",
            "result_feedback": "Approval timed out",
        }
    ]


@pytest.mark.asyncio
async def test_tool_approval_cancellation_resolves_pending_request():
    emitted = []
    recorded = []
    resolved = []
    pending: dict[str, asyncio.Future] = {}

    async def emit(event):
        emitted.append(event)

    async def record_approval(**kwargs):
        recorded.append(kwargs)

    async def resolve_approval(**kwargs):
        resolved.append(kwargs)

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(
            emit=emit,
            pending_approvals=pending,
            record_approval=record_approval,
            resolve_approval=resolve_approval,
        ),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    execution = ToolExecution(tool_id="call-1", tool_name="echo", ctx=ctx)

    task = asyncio.create_task(execution.request_approval("Echo hello", preview="hello"))
    for _ in range(20):
        if "call-1" in pending and emitted:
            break
        await asyncio.sleep(0)

    assert "call-1" in pending
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert pending == {}
    assert len(recorded) == 1
    assert resolved == [
        {
            "run_id": "run-1",
            "tool_call_id": "call-1",
            "status": "cancelled",
            "result_feedback": "Approval cancelled",
        }
    ]


@pytest.mark.asyncio
async def test_tool_approval_record_failure_still_registers_and_emits():
    emitted = []
    resolved = []
    pending: dict[str, asyncio.Future] = {}

    async def emit(event):
        emitted.append(event)

    async def record_approval(**kwargs):
        raise RuntimeError("store write failed")

    async def resolve_approval(**kwargs):
        resolved.append(kwargs)

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(
            emit=emit,
            pending_approvals=pending,
            record_approval=record_approval,
            resolve_approval=resolve_approval,
        ),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    execution = ToolExecution(tool_id="call-1", tool_name="echo", ctx=ctx)

    task = asyncio.create_task(execution.request_approval("Echo hello", preview="hello"))
    for _ in range(20):
        if "call-1" in pending and emitted:
            break
        await asyncio.sleep(0)

    assert not task.done()
    assert "call-1" in pending
    assert len(emitted) == 1

    pending["call-1"].set_result({"approved": False, "result": "no"})
    rejection = await task

    assert rejection is not None
    assert rejection.feedback == "no"
    assert pending == {}
    assert resolved[0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_tool_approval_resolve_failure_after_approval_still_continues():
    emitted = []
    pending: dict[str, asyncio.Future] = {}

    async def emit(event):
        emitted.append(event)

    async def resolve_approval(**kwargs):
        raise RuntimeError("store write failed")

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(
            emit=emit,
            pending_approvals=pending,
            resolve_approval=resolve_approval,
        ),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    execution = ToolExecution(tool_id="call-1", tool_name="echo", ctx=ctx)

    task = asyncio.create_task(execution.request_approval("Echo hello", preview="hello"))
    for _ in range(20):
        if "call-1" in pending and emitted:
            break
        await asyncio.sleep(0)

    pending["call-1"].set_result({"approved": True, "result": "ok"})

    assert await task is None
    assert pending == {}


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
                policy=READ_INTERNAL_POLICY,
            )
        },
    )

    with pytest.raises(TypeError, match="function tool handlers must return ToolResult"):
        await registry.execute("bad_output", _make_execution("bad_output"), {})


@pytest.mark.asyncio
async def test_ntrp_tool_executor_policy_offload_false_keeps_large_result_inline():
    large_content = "x" * (OFFLOAD_THRESHOLD + 1)

    async def large_result(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        return ToolResult(content=large_content, preview="large")

    registry = ToolRegistry()
    registry.register(
        "large_result",
        tool(
            description="Return a large result.",
            execute=large_result,
            policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, offload=False),
        ),
    )
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), _make_tool_context(registry))

    result = await executor.execute("large_result", {}, "call-1")

    assert result.content == large_content
    assert result.preview == "large"
    assert not result.is_error


@pytest.mark.asyncio
async def test_ntrp_tool_executor_offload_clamps_single_long_line_preview():
    large_content = "x" * (OFFLOAD_THRESHOLD + 1)

    async def large_result(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        return ToolResult(content=large_content, preview="large")

    registry = ToolRegistry()
    registry.register(
        "large_result",
        tool(
            description="Return a large result.",
            execute=large_result,
            policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
        ),
    )
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), _make_tool_context(registry))

    result = await executor.execute("large_result", {}, "call-1")

    assert len(result.content) < OFFLOAD_PREVIEW_CHARS + 500
    assert "preview truncated" in result.content
    assert "Full result offloaded" in result.content
    assert "read_file" in result.content


@pytest.mark.asyncio
async def test_ntrp_tool_executor_policy_max_result_chars_truncates_before_model_result():
    async def long_error(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        return ToolResult(content="abcdefghijklmnopqrstuvwxyz", preview="original", is_error=True)

    registry = ToolRegistry()
    registry.register(
        "long_error",
        tool(
            description="Return a long error.",
            execute=long_error,
            policy=ToolPolicy(
                action=ToolAction.READ,
                scope=ToolScope.INTERNAL,
                max_result_chars=10,
                offload=False,
            ),
        ),
    )
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), _make_tool_context(registry))

    result = await executor.execute("long_error", {}, "call-1")

    assert result.content == "abcdefghij... [truncated]"
    assert result.preview == "original"
    assert result.is_error


@pytest.mark.asyncio
async def test_ntrp_tool_executor_policy_timeout_seconds_returns_error_result():
    async def slow(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        await asyncio.sleep(1)
        return ToolResult(content="late", preview="late")

    registry = ToolRegistry()
    registry.register(
        "slow",
        tool(
            description="Return too slowly.",
            execute=slow,
            policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, timeout_seconds=0),
        ),
    )
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), _make_tool_context(registry))

    result = await executor.execute("slow", {}, "call-1")

    assert result == ToolResult(content="Tool call timed out.", preview="Timed out", is_error=True)


@pytest.mark.asyncio
async def test_ntrp_tool_executor_defaults_external_tool_timeout(monkeypatch):
    import ntrp.core.tool_executor as core_tool_executor_module

    monkeypatch.setattr(core_tool_executor_module, "DEFAULT_EXTERNAL_TOOL_TIMEOUT_SECONDS", 0.001)

    async def slow(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        await asyncio.sleep(1)
        return ToolResult(content="late", preview="late")

    registry = ToolRegistry()
    registry.register(
        "slow_external",
        tool(
            description="Return too slowly.",
            execute=slow,
            policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.EXTERNAL),
        ),
    )
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), _make_tool_context(registry))

    result = await executor.execute("slow_external", {}, "call-1")

    assert result == ToolResult(content="Tool call timed out.", preview="Timed out", is_error=True)


@pytest.mark.asyncio
async def test_ntrp_tool_executor_audits_policy_enabled_calls(session_store: SessionStore):
    async def echo(execution: ToolExecution, args: EchoInput) -> ToolResult:
        return ToolResult(content=f"echo: {args.text}", preview="ok")

    registry = ToolRegistry()
    registry.register(
        "echo",
        tool(
            description="Echo text.",
            input_model=EchoInput,
            execute=echo,
            policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, audit=True),
        ),
    )
    ctx = _make_tool_context(registry, session_id="sess-1")
    ctx.services["store"] = session_store
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), ctx)

    result = await executor.execute("echo", {"text": "hello"}, "call-1")
    rows = await session_store.list_tool_calls(run_id="run-1")

    expected_hash = hashlib.sha256(
        json.dumps({"text": "hello"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert result.preview == "ok"
    assert len(rows) == 1
    assert rows[0]["tool_call_id"] == "call-1"
    assert rows[0]["tool_name"] == "echo"
    assert rows[0]["action"] == "read"
    assert rows[0]["scope"] == "internal"
    assert rows[0]["args_hash"] == expected_hash
    assert rows[0]["status"] == "success"
    assert rows[0]["result_preview"] == "ok"


@pytest.mark.asyncio
async def test_ntrp_tool_executor_audits_cancelled_policy_enabled_call(session_store: SessionStore):
    entered = asyncio.Event()

    async def wait_forever(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        entered.set()
        await asyncio.Event().wait()
        return ToolResult(content="done", preview="done")

    registry = ToolRegistry()
    registry.register(
        "wait_forever",
        tool(
            description="Wait until cancelled.",
            execute=wait_forever,
            policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, audit=True),
        ),
    )
    ctx = _make_tool_context(registry, session_id="sess-1")
    ctx.services["store"] = session_store
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), ctx)

    task = asyncio.create_task(executor.execute("wait_forever", {}, "call-1"))
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    rows = await session_store.list_tool_calls(run_id="run-1")
    assert len(rows) == 1
    assert rows[0]["tool_call_id"] == "call-1"
    assert rows[0]["status"] == "cancelled"
    assert rows[0]["ended_at"] is not None


@pytest.mark.asyncio
async def test_ntrp_tool_executor_skips_audit_when_policy_disabled(session_store: SessionStore):
    async def echo(execution: ToolExecution, args: EchoInput) -> ToolResult:
        return ToolResult(content=f"echo: {args.text}", preview="ok")

    registry = ToolRegistry()
    registry.register(
        "echo",
        tool(
            description="Echo text.",
            input_model=EchoInput,
            execute=echo,
            policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, audit=False),
        ),
    )
    ctx = _make_tool_context(registry, session_id="sess-1")
    ctx.services["store"] = session_store
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), ctx)

    result = await executor.execute("echo", {"text": "hello"}, "call-1")

    assert result.preview == "ok"
    assert await session_store.list_tool_calls(run_id="run-1") == []


@pytest.mark.asyncio
async def test_ntrp_tool_executor_audits_rejected_approval_as_error(session_store: SessionStore):
    async def echo(execution: ToolExecution, args: EchoInput) -> ToolResult:
        return ToolResult(content=args.text, preview=args.text)

    registry = ToolRegistry()
    registry.register(
        "echo",
        tool(
            description="Echo text.",
            input_model=EchoInput,
            execute=echo,
            policy=WRITE_INTERNAL_APPROVAL_POLICY,
        ),
    )
    ctx = _make_tool_context(registry, session_id="sess-1")
    ctx.services["store"] = session_store
    executor = NtrpToolExecutor(ToolExecutor().with_registry(registry), ctx)

    result = await executor.execute("echo", {"text": "hello"}, "call-1")
    rows = await session_store.list_tool_calls(run_id="run-1")

    assert result.preview == "Rejected"
    assert rows[0]["status"] == "error"
    assert rows[0]["result_preview"] == "Rejected"


def test_tool_executor_registers_integration_tool_map(monkeypatch):
    async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        return ToolResult(content="now", preview="now")

    time_tools = {
        "current_time": tool(
            description="Get the current time.",
            execute=current_time,
            policy=READ_INTERNAL_POLICY,
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
    registry.register(
        "current_time",
        tool(description="Get the current time.", execute=current_time, policy=READ_INTERNAL_POLICY),
    )

    result = await registry.execute("current_time", _make_execution("current_time"), {})

    assert result.content == "now"
    assert calls == ["one:before", "two:before", "execute", "two:after", "one:after"]


def test_tool_registry_rejects_duplicate_tool_names():
    async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
        return ToolResult(content="now", preview="now")

    registry = ToolRegistry()
    registry.register(
        "current_time",
        tool(description="Get the current time.", execute=current_time, policy=READ_INTERNAL_POLICY),
    )

    with pytest.raises(ValueError, match="duplicate tool name"):
        registry.register(
            "current_time",
            tool(description="Get the current time.", execute=current_time, policy=READ_INTERNAL_POLICY),
        )


def test_discover_user_tools_loads_named_tool_map(tmp_path):
    (tmp_path / "custom.py").write_text(
        """
from ntrp.tools.core import EmptyInput, ToolAction, ToolPolicy, ToolResult, ToolScope, tool


async def hello(execution, args: EmptyInput) -> ToolResult:
    return ToolResult(content="hello", preview="hello")


tools = {
    "hello": tool(
        description="Say hello.",
        execute=hello,
        policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    ),
}
""".strip()
    )

    discovered = discover_user_tools(tmp_path)

    assert set(discovered) == {"hello"}
    assert discovered["hello"].to_dict("hello")["function"]["name"] == "hello"
