import asyncio
from collections.abc import AsyncGenerator, Callable
from pathlib import Path

from ntrp.constants import OFFLOAD_PREVIEW_CHARS, OFFLOAD_THRESHOLD
from ntrp.core.async_queue import AsyncQueue
from ntrp.core.events import ToolExecuted
from ntrp.core.models import PendingToolCall, ToolExecutionResult
from ntrp.events import SSEEvent, ToolCallEvent, ToolResultEvent
from ntrp.logging import get_logger
from ntrp.tools.core.base import ToolResult
from ntrp.tools.core.context import ToolContext, ToolExecution
from ntrp.tools.executor import ToolExecutor
from ntrp.utils import ms_now

_logger = get_logger(__name__)

OFFLOAD_BASE = Path("/tmp/ntrp")


class ToolRunner:
    def __init__(
        self,
        executor: ToolExecutor,
        ctx: ToolContext,
        depth: int,
        parent_id: str | None,
        is_cancelled: Callable[[], bool],
    ):
        self.executor = executor
        self.ctx = ctx
        self.depth = depth
        self.parent_id = parent_id or "root"
        self.is_cancelled = is_cancelled
        self._offload_counter = 0

    def _maybe_offload(self, tool_name: str, result: ToolResult) -> ToolResult:
        """Offload large tool results to filesystem, return compact reference.

        Manus pattern: full representation stored in file, compact reference in context.
        Agent can use read_file() to access full content if needed.
        """
        content = result.content
        if len(content) <= OFFLOAD_THRESHOLD:
            return result

        # Write full result to session-scoped temp file
        self._offload_counter += 1
        offload_dir = OFFLOAD_BASE / self.ctx.session_id / "results"
        offload_dir.mkdir(parents=True, exist_ok=True)
        offload_path = offload_dir / f"{tool_name}_{self._offload_counter}.txt"
        offload_path.write_text(content, encoding="utf-8")

        # Create compact reference for context window
        compact = content[:OFFLOAD_PREVIEW_CHARS]
        if len(content) > OFFLOAD_PREVIEW_CHARS:
            compact += f"\n\n[...{len(content) - OFFLOAD_PREVIEW_CHARS} chars offloaded → {offload_path}]"

        return ToolResult(content=compact, preview=result.preview, data=result.data)

    def _display_name(self, name: str) -> str:
        tool = self.executor.registry.get(name)
        return tool.display_name if tool else name

    def _make_start_event(self, call: PendingToolCall) -> ToolCallEvent:
        return ToolCallEvent(
            tool_id=call.tool_call.id,
            name=call.name,
            args=call.args,
            depth=self.depth,
            parent_id=self.parent_id,
            display_name=self._display_name(call.name),
        )

    def _make_result_event(
        self,
        call: PendingToolCall,
        result: ToolResult,
        duration_ms: int,
    ) -> ToolResultEvent:
        self.ctx.channel.publish(
            ToolExecuted(
                name=call.name,
                duration_ms=duration_ms,
                depth=self.depth,
                is_error=result.is_error,
                run_id=self.ctx.run_id,
            )
        )

        return ToolResultEvent(
            tool_id=call.tool_call.id,
            name=call.name,
            result=result.content,
            preview=result.preview,
            depth=self.depth,
            parent_id=self.parent_id,
            duration_ms=duration_ms,
            data=result.data,
            display_name=self._display_name(call.name),
        )

    def _needs_approval(self, call: PendingToolCall) -> bool:
        tool = self.executor.registry.get(call.name)
        if not tool or not tool.mutates:
            return False
        if self.ctx.skip_approvals:
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
            result = self._maybe_offload(call.name, result)
            duration_ms = ms_now() - start_ms
            yield self._make_result_event(call=call, result=result, duration_ms=duration_ms)
        except Exception as e:
            duration_ms = ms_now() - start_ms
            yield self._make_result_event(
                call=call,
                result=ToolResult(
                    content=f"Error: {type(e).__name__}: {e}", preview=f"Failed: {type(e).__name__}", is_error=True
                ),
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
                result = self._maybe_offload(call.name, result)
                duration_ms = ms_now() - start_ms
                results_queue.enqueue(
                    ToolExecutionResult(
                        call=call,
                        content=result.content,
                        preview=result.preview,
                        duration_ms=duration_ms,
                        is_error=result.is_error,
                        data=result.data,
                    )
                )
            except Exception as e:
                duration_ms = ms_now() - start_ms
                results_queue.enqueue(
                    ToolExecutionResult(
                        call=call,
                        content=f"Error: {type(e).__name__}: {e}",
                        preview=f"Failed: {type(e).__name__}",
                        duration_ms=duration_ms,
                        is_error=True,
                    )
                )

        async def run_all() -> None:
            try:
                async with asyncio.TaskGroup() as tg:
                    for call in calls:
                        tg.create_task(execute_tool(call))
            except ExceptionGroup as eg:
                _logger.warning("Tool execution errors: %s", [str(e) for e in eg.exceptions])
            finally:
                results_queue.finish()

        asyncio.create_task(run_all())

        async for r in results_queue:
            yield self._make_result_event(
                call=r.call,
                result=ToolResult(content=r.content, preview=r.preview, is_error=r.is_error, data=r.data),
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
