import asyncio
from typing import TYPE_CHECKING

from ntrp.events.sse import CancelledEvent, SSEEvent

if TYPE_CHECKING:
    from ntrp.server.bus import SessionBus
    from ntrp.services.chat import ChatContext


async def run_agent_loop(ctx: "ChatContext", agent, bus: "SessionBus") -> str | None:
    """Run agent loop, push events to bus. Returns final text or None if cancelled."""
    messages = ctx.run.messages
    user_message = messages[-1]["content"]
    history = messages[:-1] if len(messages) > 1 else None

    agent.ctx.io.emit = bus.emit
    # Share the same list so injected messages reach the agent
    ctx.run.messages = agent.messages

    result = ""
    try:
        async for item in agent.stream(user_message, history=history):
            if ctx.run.cancelled:
                break
            if isinstance(item, str):
                result = item
            elif isinstance(item, SSEEvent):
                await bus.emit(item)
    except asyncio.CancelledError:
        result = ""

    if ctx.run.cancelled:
        await bus.emit(CancelledEvent(run_id=ctx.run.run_id))
        return None

    return result
