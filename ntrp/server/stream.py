import asyncio
import json
from contextlib import suppress

from ntrp.events import CancelledEvent, SSEEvent
from ntrp.server.chat import ChatContext


def to_sse(event: SSEEvent | dict) -> str:
    if isinstance(event, SSEEvent):
        return event.to_sse_string()
    return f"data: {json.dumps(event)}\n\n"


async def run_agent_loop(ctx: ChatContext, agent, user_message: str):
    """Run agent and yield SSE strings. Yields dict with result at end.

    Uses a merged event stream pattern:
    - Agent runs in background task, pushing events to a shared queue
    - Subagent/tool events also go to the same queue via event_bus forwarding
    - Consumer yields events as they arrive in true real-time
    """
    history = ctx.messages[:-1] if len(ctx.messages) > 1 else None

    _DONE = object()
    _ERROR = object()

    merged_queue: asyncio.Queue = asyncio.Queue()
    result: str = ""
    error: Exception | None = None

    async def forward_event_bus():
        while True:
            try:
                event = await asyncio.wait_for(ctx.event_bus.get(), timeout=0.05)
                await merged_queue.put(("event_bus", event))
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                while not ctx.event_bus.empty():
                    try:
                        event = ctx.event_bus.get_nowait()
                        await merged_queue.put(("event_bus", event))
                    except asyncio.QueueEmpty:
                        break
                raise

    async def run_agent():
        nonlocal result, error
        try:
            async for item in agent.stream(user_message, history=history):
                if isinstance(item, str):
                    result = item
                elif isinstance(item, SSEEvent):
                    await merged_queue.put(("agent", item))
        except Exception as e:
            error = e
            await merged_queue.put((_ERROR, e))
        finally:
            await merged_queue.put((_DONE, None))

    agent_task = asyncio.create_task(run_agent())
    forwarder_task = asyncio.create_task(forward_event_bus())

    try:
        while True:
            if ctx.run.cancelled:
                yield to_sse(CancelledEvent(run_id=ctx.run.run_id))
                return

            try:
                source, item = await asyncio.wait_for(merged_queue.get(), timeout=0.1)
            except TimeoutError:
                if agent_task.done():
                    while not merged_queue.empty():
                        source, item = merged_queue.get_nowait()
                        if source == _DONE:
                            break
                        if source == _ERROR:
                            raise item
                        if isinstance(item, SSEEvent):
                            yield to_sse(item)
                    break
                continue

            if source == _DONE:
                while not merged_queue.empty():
                    _src, evt = merged_queue.get_nowait()
                    if isinstance(evt, SSEEvent):
                        yield to_sse(evt)
                break

            if source == _ERROR:
                raise item

            if isinstance(item, SSEEvent):
                yield to_sse(item)

    finally:
        forwarder_task.cancel()
        with suppress(asyncio.CancelledError):
            await forwarder_task

        while not merged_queue.empty():
            try:
                _src, evt = merged_queue.get_nowait()
                if isinstance(evt, SSEEvent):
                    yield to_sse(evt)
            except asyncio.QueueEmpty:
                break

        if not agent_task.done():
            agent_task.cancel()
            with suppress(asyncio.CancelledError):
                await agent_task

    if error:
        raise error

    yield {"_result": result}
