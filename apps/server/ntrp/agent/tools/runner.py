import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator
from contextlib import nullcontext
from dataclasses import dataclass

from ntrp.agent.tools.executor import AgentToolExecutor
from ntrp.agent.types.events import ToolCompleted, ToolStarted
from ntrp.agent.types.tool_call import PendingToolCall
from ntrp.agent.types.tools import ToolResult

_SENTINEL = object()


@dataclass(frozen=True)
class _ResolvedCall:
    call: PendingToolCall
    display_name: str
    kind: str = "tool"


@dataclass(frozen=True)
class _ConcurrentResult:
    resolved: _ResolvedCall
    result: ToolResult
    duration_ms: int


def _ms_now() -> int:
    return int(time.monotonic() * 1000)


class ToolRunner:
    def __init__(self, executor: AgentToolExecutor, depth: int, parent_id: str | None, tracer: object | None = None):
        self._executor = executor
        self._depth = depth
        self._parent_id = parent_id
        self._tracer = tracer

    def _resolve(self, call: PendingToolCall) -> _ResolvedCall:
        meta = self._executor.get_meta(call.name)
        return _ResolvedCall(
            call=call,
            display_name=meta.display_name if meta else call.name,
            kind=meta.kind if meta else "tool",
        )

    async def _run_one(self, rc: _ResolvedCall) -> tuple[ToolResult, int]:
        start_ms = _ms_now()
        cm = (
            self._tracer.observation(name=f"tool.{rc.call.name}", as_type="span", input=rc.call.args)
            if self._tracer is not None
            else nullcontext()
        )
        with cm as observation:
            try:
                result = await self._executor.execute(rc.call.name, rc.call.args, rc.call.tool_call.id)
                if observation is not None:
                    update = {
                        "output": result.content,
                        "metadata": {
                            "tool_id": rc.call.tool_call.id,
                            "tool_name": rc.call.name,
                            "is_error": result.is_error,
                        },
                    }
                    if result.is_error:
                        update["level"] = "ERROR"
                    observation.update(**update)
                return result, _ms_now() - start_ms
            except Exception as e:
                if observation is not None:
                    observation.update(
                        output=f"{type(e).__name__}: {e}",
                        metadata={"tool_id": rc.call.tool_call.id, "tool_name": rc.call.name},
                        level="ERROR",
                        status_message=str(e),
                    )
                return (
                    ToolResult(
                        content=f"Error: {type(e).__name__}: {e}",
                        preview=f"Failed: {type(e).__name__}",
                        is_error=True,
                    ),
                    _ms_now() - start_ms,
                )

    def _started(self, rc: _ResolvedCall) -> ToolStarted:
        return ToolStarted(
            tool_id=rc.call.tool_call.id,
            name=rc.call.name,
            args=rc.call.args,
            depth=self._depth,
            parent_id=self._parent_id,
            display_name=rc.display_name,
            kind=rc.kind,
        )

    def _completed(self, rc: _ResolvedCall, result: ToolResult, duration_ms: int) -> ToolCompleted:
        return ToolCompleted(
            tool_id=rc.call.tool_call.id,
            name=rc.call.name,
            result=result.content,
            preview=result.preview,
            depth=self._depth,
            parent_id=self._parent_id,
            duration_ms=duration_ms,
            is_error=result.is_error,
            data=result.data,
            display_name=rc.display_name,
            kind=rc.kind,
            model_content=result.model_content,
            source_ref=result.source_ref,
        )

    async def execute_all(self, calls: list[PendingToolCall]) -> AsyncGenerator[ToolStarted | ToolCompleted]:
        """Run every tool the model emitted in this step in parallel.

        Approvals are routed per `tool_id` via `IOBridge.pending_approvals`,
        so multiple mutating tools can each await their own approval
        Future without racing on a shared queue. Tools that don't need
        approval (or have skip_approvals/auto_approve) just run straight
        through. Either way, results stream back in completion order via
        `queue` while every tool's `started` event fires up front.
        """
        resolved = [self._resolve(c) for c in calls]
        if not resolved:
            return

        queue: asyncio.Queue[_ConcurrentResult | object] = asyncio.Queue()

        for rc in resolved:
            yield self._started(rc)

        async def run_one(rc: _ResolvedCall) -> None:
            result, duration_ms = await self._run_one(rc)
            await queue.put(_ConcurrentResult(resolved=rc, result=result, duration_ms=duration_ms))

        async def run_all() -> None:
            try:
                async with asyncio.TaskGroup() as tg:
                    for rc in resolved:
                        tg.create_task(run_one(rc))
            finally:
                await queue.put(_SENTINEL)

        task = asyncio.create_task(run_all())

        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield self._completed(item.resolved, item.result, item.duration_ms)
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
