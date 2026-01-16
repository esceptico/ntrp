import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING

from ntrp.core.async_queue import AsyncQueue
from ntrp.core.models import PendingToolCall, ToolExecutionResult
from ntrp.events import SSEEvent, ToolCallEvent, ToolResultEvent
from ntrp.tools.core import ToolContext, ToolExecution, ToolResult
from ntrp.utils import ms_now

if TYPE_CHECKING:
    from ntrp.tools.executor import ToolExecutor


class ToolRunner:
    def __init__(
        self,
        executor: "ToolExecutor",
        ctx: ToolContext,
        depth: int,
        parent_id: str | None,
        is_cancelled: Callable[[], bool],
    ):
        self.executor = executor
        self.ctx = ctx
        self.depth = depth
        self.parent_id = parent_id or ""
        self.is_cancelled = is_cancelled

    def _make_start_event(self, call: PendingToolCall) -> ToolCallEvent:
        return ToolCallEvent(
            tool_id=call.tool_call.id,
            name=call.name,
            args=call.args,
            depth=self.depth,
            parent_id=self.parent_id,
        )

    def _make_result_event(
        self,
        call: PendingToolCall,
        result: ToolResult,
        duration_ms: int,
    ) -> ToolResultEvent:
        return ToolResultEvent(
            tool_id=call.tool_call.id,
            name=call.name,
            result=result.content,
            preview=result.preview,
            depth=self.depth,
            parent_id=self.parent_id,
            duration_ms=duration_ms,
            metadata=result.metadata,
        )

    def _needs_approval(self, call: PendingToolCall) -> bool:
        tool = self.executor.registry.get(call.name)
        if not tool or not tool.mutates:
            return False
        if self.ctx.yolo:
            return False
        if call.name in self.ctx.auto_approve:
            return False
        return True

    async def _execute_single(self, call: PendingToolCall) -> AsyncGenerator[SSEEvent]:
        yield self._make_start_event(call)

        start_ms = ms_now()
        try:
            execution = ToolExecution(call.tool_call.id, call.name, self.ctx)
            result = await self.executor.execute(call.name, call.args, execution)
            duration_ms = ms_now() - start_ms
            yield self._make_result_event(call=call, result=result, duration_ms=duration_ms)
        except Exception as e:
            duration_ms = ms_now() - start_ms
            yield self._make_result_event(
                call=call,
                result=ToolResult(f"Error: {type(e).__name__}: {e}", f"Failed: {type(e).__name__}"),
                duration_ms=duration_ms,
            )

    async def _execute_concurrent(self, calls: list[PendingToolCall]) -> AsyncGenerator[SSEEvent]:
        results_queue: AsyncQueue[ToolExecutionResult] = AsyncQueue()

        for call in calls:
            yield self._make_start_event(call)

        async def execute_tool(call: PendingToolCall) -> None:
            start_ms = ms_now()
            try:
                execution = ToolExecution(call.tool_call.id, call.name, self.ctx)
                result = await self.executor.execute(call.name, call.args, execution)
                duration_ms = ms_now() - start_ms
                results_queue.enqueue(
                    ToolExecutionResult(
                        call=call,
                        content=result.content,
                        preview=result.preview,
                        metadata=result.metadata,
                        duration_ms=duration_ms,
                    )
                )
            except Exception as e:
                duration_ms = ms_now() - start_ms
                results_queue.enqueue(
                    ToolExecutionResult(
                        call=call,
                        content=f"Error: {type(e).__name__}: {e}",
                        preview=f"Failed: {type(e).__name__}",
                        metadata=None,
                        duration_ms=duration_ms,
                    )
                )

        async def run_all() -> None:
            try:
                async with asyncio.TaskGroup() as tg:
                    for call in calls:
                        tg.create_task(execute_tool(call))
            except ExceptionGroup:
                pass
            finally:
                results_queue.finish()

        asyncio.create_task(run_all())

        async for r in results_queue:
            yield self._make_result_event(
                call=r.call,
                result=ToolResult(r.content, r.preview, r.metadata),
                duration_ms=r.duration_ms,
            )

    async def _execute_sequential(self, calls: list[PendingToolCall]) -> AsyncGenerator[SSEEvent]:
        for call in calls:
            if self.is_cancelled():
                return
            async for event in self._execute_single(call):
                yield event

    async def execute_all(self, calls: list[PendingToolCall]) -> AsyncGenerator[SSEEvent]:
        def partition(pred, items):
            yes, no = [], []
            for item in items:
                (yes if pred(item) else no).append(item)
            return yes, no

        needs_approval, auto_approved = partition(self._needs_approval, calls)

        for batch, executor in [
            (auto_approved, self._execute_concurrent),
            (needs_approval, self._execute_sequential),
        ]:
            if not batch:
                continue
            async for event in executor(batch):
                yield event
