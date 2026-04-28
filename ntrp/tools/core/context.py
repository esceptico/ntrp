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


@dataclass
class IOBridge:
    """Communication channels to the UI."""

    emit: Callable[[Any], Awaitable[None]] | None = None
    approval_queue: asyncio.Queue[ApprovalResponse] | None = None


RESULT_BASE = Path(NTRP_TMP_BASE)


@dataclass
class BackgroundTaskRegistry:
    """Tracks background tasks and injects results into the agent loop."""

    session_id: str = ""
    on_result: Callable[[list[dict]], Awaitable[None]] | None = None
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

    async def deliver_result(
        self,
        task_id: str,
        result: str,
        label: str,
        status: str,
        emit: Callable[[Any], Awaitable[None]] | None,
    ) -> None:
        self._write_result_file(task_id, result)

        notification = f"[background task {task_id} {status}]"
        messages = [{"role": Role.USER, "content": notification}]

        if emit:
            await emit(BackgroundTaskEvent(task_id=task_id, command=label, status=status))

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

        if not self.ctx.io.emit or not self.ctx.io.approval_queue:
            return Rejection(feedback="No UI connected — cannot approve")

        await self.ctx.io.emit(
            ApprovalNeededEvent(
                tool_id=self.tool_id,
                name=self.tool_name,
                path=description,
                diff=diff,
                content_preview=preview if not diff else None,
            )
        )

        response = await self.ctx.io.approval_queue.get()

        if not response["approved"]:
            feedback = response.get("result", "").strip() or None
            return Rejection(feedback=feedback)

        return None
