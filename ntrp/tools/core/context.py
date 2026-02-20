import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.events.sse import ApprovalNeededEvent, ChoiceEvent

if TYPE_CHECKING:
    from ntrp.memory.facts import FactMemory
    from ntrp.sources.base import Source
    from ntrp.tools.core.base import ToolResult
    from ntrp.tools.core.registry import ToolRegistry


class ApprovalResponse(TypedDict):
    approved: bool
    result: str


class ChoiceResponse(TypedDict):
    selected: list[str]


@dataclass
class Rejection:
    feedback: str | None

    def to_result(self) -> "ToolResult":
        from ntrp.tools.core.base import ToolResult

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
    explore_model: str | None = None


@dataclass
class IOBridge:
    """Communication channels to the UI."""

    emit: Callable[[Any], Awaitable[None]] | None = None
    approval_queue: asyncio.Queue[ApprovalResponse] | None = None
    choice_queue: asyncio.Queue[ChoiceResponse] | None = None


@dataclass
class ToolContext:
    """Shared context for tool execution."""

    session_state: SessionState
    registry: "ToolRegistry"
    run: RunContext
    io: IOBridge
    memory: "FactMemory | None" = None
    sources: "dict[str, Source]" = field(default_factory=dict)
    channel: Channel = field(default_factory=Channel)
    spawn_fn: Callable[..., Awaitable[str]] | None = None

    @property
    def session_id(self) -> str:
        return self.session_state.session_id

    @property
    def skip_approvals(self) -> bool:
        return self.session_state.skip_approvals

    @property
    def auto_approve(self) -> set[str]:
        return self.session_state.auto_approve | self.run.extra_auto_approve

    def get_source[T](self, source_type: type[T]) -> T | None:
        for s in self.sources.values():
            if isinstance(s, source_type):
                return s
        return None


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
            return None

        await self.ctx.io.emit(
            ApprovalNeededEvent(
                tool_id=self.tool_id,
                name=self.tool_name,
                path=description,
                diff=diff,
                content_preview=preview if not diff else None,
            )
        )

        try:
            response = await asyncio.wait_for(self.ctx.io.approval_queue.get(), timeout=300)
        except TimeoutError:
            return Rejection(feedback="Approval timed out")

        if not response["approved"]:
            feedback = response.get("result", "").strip() or None
            return Rejection(feedback=feedback)

        return None

    async def ask_choice(
        self,
        question: str,
        options: list[dict],
        allow_multiple: bool = False,
    ) -> list[str]:
        if not self.ctx.io.emit or not self.ctx.io.choice_queue:
            return []

        await self.ctx.io.emit(
            ChoiceEvent(
                tool_id=self.tool_id,
                question=question,
                options=options,
                allow_multiple=allow_multiple,
            )
        )

        try:
            response = await asyncio.wait_for(self.ctx.io.choice_queue.get(), timeout=300)
        except TimeoutError:
            return []
        return response["selected"]
