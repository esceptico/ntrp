import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator
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
    mutates: bool


@dataclass(frozen=True)
class _ConcurrentResult:
    resolved: _ResolvedCall
    result: ToolResult
    duration_ms: int


def _ms_now() -> int:
    return int(time.monotonic() * 1000)


class ToolRunner:
    def __init__(self, executor: AgentToolExecutor):
        self._executor = executor

    def _resolve(self, call: PendingToolCall) -> _ResolvedCall:
        meta = self._executor.get_meta(call.name)
        return _ResolvedCall(
            call=call,
            display_name=meta.display_name if meta else call.name,
            mutates=meta.mutates if meta else False,
        )

    async def _run_one(self, rc: _ResolvedCall) -> tuple[ToolResult, int]:
        start_ms = _ms_now()
        try:
            result = await self._executor.execute(rc.call.name, rc.call.args)
            return result, _ms_now() - start_ms
        except Exception as e:
            return (
                ToolResult(
                    content=f"Error: {type(e).__name__}: {e}",
                    preview=f"Failed: {type(e).__name__}",
                    is_error=True,
                ),
                _ms_now() - start_ms,
            )

    @staticmethod
    def _started(rc: _ResolvedCall) -> ToolStarted:
        return ToolStarted(
            tool_id=rc.call.tool_call.id,
            name=rc.call.name,
            args=rc.call.args,
            display_name=rc.display_name,
        )

    @staticmethod
    def _completed(rc: _ResolvedCall, result: ToolResult, duration_ms: int) -> ToolCompleted:
        return ToolCompleted(
            tool_id=rc.call.tool_call.id,
            name=rc.call.name,
            result=result.content,
            preview=result.preview,
            duration_ms=duration_ms,
            is_error=result.is_error,
            data=result.data,
            display_name=rc.display_name,
        )

    async def _execute_sequential(self, resolved: list[_ResolvedCall]) -> AsyncGenerator[ToolStarted | ToolCompleted]:
        for rc in resolved:
            yield self._started(rc)
            result, duration_ms = await self._run_one(rc)
            yield self._completed(rc, result, duration_ms)

    async def _execute_concurrent(self, resolved: list[_ResolvedCall]) -> AsyncGenerator[ToolStarted | ToolCompleted]:
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

    async def execute_all(self, calls: list[PendingToolCall]) -> AsyncGenerator[ToolStarted | ToolCompleted]:
        resolved = [self._resolve(c) for c in calls]
        mutating = [rc for rc in resolved if rc.mutates]
        non_mutating = [rc for rc in resolved if not rc.mutates]

        if non_mutating:
            async for event in self._execute_concurrent(non_mutating):
                yield event
        if mutating:
            async for event in self._execute_sequential(mutating):
                yield event
