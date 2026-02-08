import asyncio
import json
from contextlib import suppress
from ntrp.events import CancelledEvent, SSEEvent
from ntrp.server.chat import ChatContext


def to_sse(event: SSEEvent | dict) -> str:
    if isinstance(event, SSEEvent):
        return event.to_sse_string()
    return f"data: {json.dumps(event)}\n\n"


class _Done: pass


class _Error:
    def __init__(self, exception: Exception):
        self.exception = exception


type QueueItem = SSEEvent | _Done | _Error


async def run_agent_loop(ctx: ChatContext, agent, user_message: str):
    """Run agent and yield SSE strings. Yields dict with result at end.

    All events (agent, tool, subagent) flow through a single merged queue.
    Tools emit directly into the queue — no polling bridge needed.
    """
    history = ctx.messages[:-1] if len(ctx.messages) > 1 else None

    merged_queue: asyncio.Queue[QueueItem] = asyncio.Queue()
    result: str = ""
    error: Exception | None = None

    # Wire tool/subagent emit directly into the merged queue
    agent.ctx.emit = merged_queue.put

    async def run_agent():
        nonlocal result, error
        try:
            async for item in agent.stream(user_message, history=history):
                if isinstance(item, str):
                    result = item
                elif isinstance(item, SSEEvent):
                    await merged_queue.put(item)
        except Exception as e:
            error = e
            await merged_queue.put(_Error(e))
        finally:
            await merged_queue.put(_Done())

    agent_task = asyncio.create_task(run_agent())

    def _drain_remaining():
        events = []
        while not merged_queue.empty():
            match merged_queue.get_nowait():
                case _Done():
                    break
                case _Error(exception=e):
                    raise e
                case event:
                    events.append(event)
        return events

    try:
        while True:
            if ctx.run.cancelled:
                yield to_sse(CancelledEvent(run_id=ctx.run.run_id))
                return

            try:
                item = await asyncio.wait_for(merged_queue.get(), timeout=0.1)
            except TimeoutError:
                if agent_task.done():
                    for evt in _drain_remaining():
                        yield to_sse(evt)
                    break
                continue

            match item:
                case _Done():
                    for evt in _drain_remaining():
                        yield to_sse(evt)
                    break
                case _Error(exception=e):
                    raise e
                case event:
                    yield to_sse(event)

    finally:
        while not merged_queue.empty():
            try:
                item = merged_queue.get_nowait()
                if isinstance(item, SSEEvent):
                    yield to_sse(item)
            except asyncio.QueueEmpty:
                break

        if not agent_task.done():
            agent_task.cancel()
            with suppress(asyncio.CancelledError):
                await agent_task

    if error:
        raise error

    yield {"_result": result}
