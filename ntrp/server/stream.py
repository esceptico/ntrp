import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from ntrp.events.sse import CancelledEvent, SSEEvent

if TYPE_CHECKING:
    from ntrp.core.agent import Agent
    from ntrp.server.bus import SessionBus
    from ntrp.services.chat import ChatContext


async def run_agent_loop(
    ctx: "ChatContext", agent: "Agent", bus: "SessionBus"
) -> tuple[str | None, AsyncGenerator | None]:
    """Run agent loop, push events to bus.

    Returns (result_text, None) on normal completion,
    (None, None) on cancellation,
    (None, generator) when backgrounded (caller should drain the generator).
    """
    messages = ctx.run.messages
    user_message = messages[-1]["content"]
    history = messages[:-1] if len(messages) > 1 else None

    agent.ctx.io.emit = bus.emit
    ctx.run.messages = agent.messages

    result = ""
    gen = agent.stream(user_message, history=history)
    try:
        async for item in gen:
            if ctx.run.cancelled:
                break
            if ctx.run.backgrounded:
                return None, gen
            if isinstance(item, str):
                result = item
            elif isinstance(item, SSEEvent):
                await bus.emit(item)
    except asyncio.CancelledError:
        result = ""

    if ctx.run.cancelled:
        await bus.emit(CancelledEvent(run_id=ctx.run.run_id))
        return None, None

    return result, None
