import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from ntrp.events.sse import AgentResult, CancelledEvent, SSEEvent

if TYPE_CHECKING:
    from ntrp.services.chat import ChatContext


async def run_agent_loop(ctx: "ChatContext", agent):
    """Run agent and yield SSE strings. Yields AgentResult at end.

    Events from agent.stream() and tool/subagent emissions merge through a single queue.
    None sentinel signals the agent task is done.
    """
    messages = ctx.run.messages
    user_message = messages[-1]["content"]
    history = messages[:-1] if len(messages) > 1 else None

    queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
    agent.ctx.io.emit = queue.put

    async def _run() -> str:
        result = ""
        try:
            async for item in agent.stream(user_message, history=history):
                if isinstance(item, str):
                    result = item
                elif isinstance(item, SSEEvent):
                    await queue.put(item)
        finally:
            await queue.put(None)
        return result

    task = asyncio.create_task(_run())

    try:
        while True:
            if ctx.run.cancelled:
                yield CancelledEvent(run_id=ctx.run.run_id).to_sse_string()
                return

            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                if task.done():
                    break
                continue

            if event is None:
                break
            yield event.to_sse_string()

        # Drain remaining events
        while not queue.empty():
            if (event := queue.get_nowait()) is not None:
                yield event.to_sse_string()

        # Re-raise agent errors
        if task.done() and not task.cancelled() and task.exception():
            raise task.exception()

        yield AgentResult(text=task.result())

    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
