import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from coolname import generate_slug

from ntrp.agent import Role, ToolResult
from ntrp.agent.ledger import SharedLedger
from ntrp.constants import NTRP_TMP_BASE
from ntrp.context.models import SessionState
from ntrp.events.sse import ApprovalNeededEvent, BackgroundTaskEvent
from ntrp.logging import get_logger

_logger = get_logger(__name__)

if TYPE_CHECKING:
    from ntrp.tools.core.registry import ToolRegistry


class ApprovalResponse(TypedDict):
    approved: bool
    result: str


@dataclass
class Rejection:
    feedback: str | None

    def to_result(self) -> ToolResult:
        content = (
            f"User rejected this action and said: {self.feedback}" if self.feedback else "User rejected this action"
        )
        return ToolResult(content=content, preview="Rejected")


@dataclass
class RunContext:
    """Per-run identity and limits."""

    run_id: str
    current_depth: int = 0
    max_depth: int = 0
    extra_auto_approve: set[str] = field(default_factory=set)
    research_model: str | None = None
    deferred_tools_enabled: bool = False
    loaded_tools: set[str] = field(default_factory=set)
    allowed_tool_names: set[str] | None = None
    loop_task_id: str | None = None


@dataclass
class IOBridge:
    """Communication channels to the UI."""

    emit: Callable[[Any], Awaitable[None]] | None = None
    # Per-tool approval response routing. Each tool that needs approval
    # registers `pending_approvals[tool_id] = Future()` and awaits it;
    # the /tools/result endpoint resolves the matching Future.
    pending_approvals: dict[str, "asyncio.Future[ApprovalResponse]"] | None = None


RESULT_BASE = Path(NTRP_TMP_BASE)


@dataclass
class BackgroundTaskRegistry:
    """Tracks background tasks and injects results into the agent loop."""

    session_id: str = ""
    on_result: Callable[[list[dict]], Awaitable[None]] | None = None
    record_event: Callable[..., Awaitable[None]] | None = None
    read_result: Callable[[str], Awaitable[str | None]] | None = None
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _commands: dict[str, str] = field(default_factory=dict)

    def generate_id(self) -> str:
        return generate_slug(2)

    def _remove(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._commands.pop(task_id, None)

    def register(self, task_id: str, task: asyncio.Task, command: str) -> None:
        self._tasks[task_id] = task
        self._commands[task_id] = command
        task.add_done_callback(lambda _: self._remove(task_id))

    async def _record(
        self,
        *,
        task_id: str,
        status: str,
        detail: str | None = None,
        result_ref: str | None = None,
        result_text: str | None = None,
        parent_run_id: str | None = None,
    ) -> None:
        if not self.record_event:
            return
        terminal = status in {"completed", "failed", "cancelled", "interrupted"}
        await self.record_event(
            task_id=task_id,
            session_id=self.session_id,
            parent_run_id=parent_run_id,
            command=self._commands.get(task_id, ""),
            status=status,
            detail=detail,
            result_ref=result_ref,
            result_text=result_text,
            terminal=terminal,
        )

    async def record_started(self, *, task_id: str, command: str, parent_run_id: str | None = None) -> None:
        self._commands[task_id] = command
        await self._record(
            task_id=task_id,
            status="started",
            parent_run_id=parent_run_id,
        )

    async def record_activity(self, task_id: str, detail: str) -> None:
        await self._record(task_id=task_id, status="activity", detail=detail)

    def cancel_all(self) -> list[tuple[str, str]]:
        """Cancel all pending tasks. Returns list of (task_id, command) for cancelled tasks."""
        cancelled: list[tuple[str, str]] = []
        for task_id, task in list(self._tasks.items()):
            if not task.done():
                command = self._commands.get(task_id, "")
                cancelled.append((task_id, command))
                task.cancel()
        return cancelled

    def cancel(self, task_id: str) -> str | None:
        """Cancel a single task. Returns the command if cancelled, None if not found or already done."""
        task = self._tasks.get(task_id)
        if task is None or task.done():
            return None
        command = self._commands.get(task_id, "")
        task.cancel()
        return command

    def list_pending(self) -> list[tuple[str, str]]:
        return [(tid, self._commands[tid]) for tid, t in self._tasks.items() if not t.done()]

    async def inject(self, messages: list[dict]) -> None:
        if self.on_result:
            await self.on_result(messages)
        else:
            _logger.warning("Background task result dropped — on_result not wired")

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    def _write_result_file(self, task_id: str, content: str) -> Path:
        result_dir = RESULT_BASE / self.session_id / "bg_results"
        result_dir.mkdir(parents=True, exist_ok=True)
        path = result_dir / f"{task_id}.txt"
        path.write_text(content, encoding="utf-8")
        return path

    async def read_background_result(self, task_id: str) -> str | None:
        if self.read_result:
            durable = await self.read_result(task_id)
            if durable is not None:
                return durable
        path = RESULT_BASE / self.session_id / "bg_results" / f"{task_id}.txt"
        if not path.exists():
            return None
        return await asyncio.to_thread(path.read_text, encoding="utf-8")

    async def deliver_result(
        self,
        task_id: str,
        result: str,
        label: str,
        status: str,
        emit: Callable[[Any], Awaitable[None]] | None,
    ) -> None:
        path = self._write_result_file(task_id, result)
        result_ref = str(path.relative_to(RESULT_BASE / self.session_id))

        notification = f"[background agent {task_id} {status}]\n\nResult:\n{result}"
        messages = [
            {
                "role": Role.USER,
                "content": notification,
                "is_meta": True,
                "client_id": f"bg:{task_id}:{status}",
            }
        ]

        if emit:
            await emit(
                BackgroundTaskEvent(
                    task_id=task_id,
                    session_id=self.session_id,
                    command=label,
                    status=status,
                    result_ref=result_ref,
                    terminal=True,
                )
            )

        await self._record(
            task_id=task_id,
            status=status,
            result_ref=result_ref,
            result_text=result,
        )

        await self.inject(messages)


@dataclass
class ToolContext:
    """Shared context for tool execution."""

    session_state: SessionState
    registry: "ToolRegistry"
    run: RunContext
    io: IOBridge
    services: dict[str, Any] = field(default_factory=dict)
    ledger: SharedLedger | None = None
    spawn_fn: Callable[..., Awaitable[str]] | None = None
    background_tasks: BackgroundTaskRegistry = field(default_factory=BackgroundTaskRegistry)

    @property
    def session_id(self) -> str:
        return self.session_state.session_id

    @property
    def skip_approvals(self) -> bool:
        return self.session_state.skip_approvals

    @property
    def auto_approve(self) -> set[str]:
        return self.session_state.auto_approve | self.run.extra_auto_approve

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(self.services)

    def get_client[T](self, id: str, client_type: type[T]) -> T | None:
        s = self.services.get(id)
        return s if isinstance(s, client_type) else None


@dataclass
class ToolExecution:
    """Per-tool execution context. Pairs tool identity with shared context."""

    tool_id: str
    tool_name: str
    ctx: ToolContext

    async def request_approval(
        self,
        description: str,
        *,
        diff: str | None = None,
        preview: str | None = None,
    ) -> Rejection | None:
        if self.ctx.skip_approvals or self.tool_name in self.ctx.auto_approve:
            return None

        if not self.ctx.io.emit or self.ctx.io.pending_approvals is None:
            return Rejection(feedback="No UI connected — cannot approve")

        # Register a Future scoped to THIS tool_id and await it. Multiple
        # tools approving in parallel each wait on their own Future, so
        # responses don't race a shared queue.
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalResponse] = loop.create_future()
        self.ctx.io.pending_approvals[self.tool_id] = future

        try:
            await self.ctx.io.emit(
                ApprovalNeededEvent(
                    tool_id=self.tool_id,
                    name=self.tool_name,
                    path=description,
                    diff=diff,
                    content_preview=preview if not diff else None,
                )
            )
            response = await future
        finally:
            self.ctx.io.pending_approvals.pop(self.tool_id, None)

        if not response["approved"]:
            feedback = response.get("result", "").strip() or None
            return Rejection(feedback=feedback)

        return None
