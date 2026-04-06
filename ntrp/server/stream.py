import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from ntrp.agent import Result
from ntrp.events.sse import RunCancelledEvent, agent_event_to_sse

if TYPE_CHECKING:
    from ntrp.agent import Agent
    from ntrp.server.bus import SessionBus
    from ntrp.services.chat import ChatContext


async def run_agent_loop(
    ctx: "ChatContext", agent: "Agent", bus: "SessionBus"
) -> tuple[str | None, AsyncGenerator | None]:
    messages = ctx.run.messages

    result = ""
    gen = agent.stream(messages)
    try:
        async for item in gen:
            if ctx.run.cancelled:
                break
            if ctx.run.backgrounded:
                return None, gen
            if isinstance(item, Result):
                result = item.text
            else:
                sse = agent_event_to_sse(item)
                if sse:
                    await bus.emit(sse)
                    await asyncio.sleep(0)
    except asyncio.CancelledError:
        result = ""

    if ctx.run.cancelled:
        await bus.emit(RunCancelledEvent(run_id=ctx.run.run_id))
        return None, None

    return result, None
