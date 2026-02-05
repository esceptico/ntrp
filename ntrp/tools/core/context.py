import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

from ntrp.context.models import SessionState
from ntrp.events import ApprovalNeededEvent, ChoiceEvent

if TYPE_CHECKING:
    from ntrp.tools.executor import ToolExecutor


# subset of response from POST /tools/result endpoint in app.py
class ApprovalResponse(TypedDict):
    approved: bool


class ChoiceResponse(TypedDict):
    selected: list[str]


class PermissionDenied(Exception):
    def __init__(self, tool_name: str, description: str):
        self.tool_name = tool_name
        self.description = description
        super().__init__(f"Permission denied: {tool_name} '{description}'")


@dataclass
class ToolContext:
    """Shared context for tool execution. Stateless, one per request."""

    session_state: SessionState
    executor: "ToolExecutor"

    emit: Callable[[Any], Awaitable[None]] | None = None
    approval_queue: asyncio.Queue[ApprovalResponse] | None = None
    choice_queue: asyncio.Queue[ChoiceResponse] | None = None
    spawn_fn: Callable[..., Awaitable[str]] | None = None

    extra_auto_approve: set[str] = field(default_factory=set)

    @property
    def session_id(self) -> str:
        return self.session_state.session_id

    @property
    def yolo(self) -> bool:
        return self.session_state.yolo

    @property
    def auto_approve(self) -> set[str]:
        return self.session_state.auto_approve | self.extra_auto_approve


@dataclass
class ToolExecution:
    """Per-tool execution context. Pairs tool identity with shared context."""

    tool_id: str
    tool_name: str
    ctx: ToolContext

    async def require_approval(
        self,
        description: str,
        *,
        diff: str | None = None,
        preview: str | None = None,
    ) -> None:
        if self.ctx.yolo or self.tool_name in self.ctx.auto_approve:
            return

        if not self.ctx.emit or not self.ctx.approval_queue:
            return

        await self.ctx.emit(
            ApprovalNeededEvent(
                tool_id=self.tool_id,
                name=self.tool_name,
                path=description,
                diff=diff,
                content_preview=preview if not diff else None,
            )
        )

        response = await self.ctx.approval_queue.get()
        if not response["approved"]:
            raise PermissionDenied(self.tool_name, description)

    async def ask_choice(
        self,
        question: str,
        options: list[dict],
        allow_multiple: bool = False,
    ) -> list[str]:
        """Emit choice event and wait for user selection. Returns list of selected option ids."""
        if not self.ctx.emit or not self.ctx.choice_queue:
            return []

        await self.ctx.emit(
            ChoiceEvent(
                tool_id=self.tool_id,
                question=question,
                options=options,
                allow_multiple=allow_multiple,
            )
        )

        response = await self.ctx.choice_queue.get()
        return response["selected"]
