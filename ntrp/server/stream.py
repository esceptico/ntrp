import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from ntrp.agent import Result, TextBlock, TextDelta, ToolCompleted, ToolStarted
from ntrp.events.sse import RunCancelledEvent, TextDeltaEvent, TextEvent, ToolCallEvent, ToolResultEvent

if TYPE_CHECKING:
    from ntrp.agent import Agent
    from ntrp.server.bus import SessionBus
    from ntrp.services.chat import ChatContext


def _to_sse(event: TextDelta | TextBlock | ToolStarted | ToolCompleted):
    match event:
        case TextDelta(content=content):
            return TextDeltaEvent(content=content)
        case TextBlock(content=content):
            return TextEvent(content=content)
        case ToolStarted():
            return ToolCallEvent(
                tool_id=event.tool_id,
                name=event.name,
                args=event.args,
                display_name=event.display_name,
            )
        case ToolCompleted():
            return ToolResultEvent(
                tool_id=event.tool_id,
                name=event.name,
                result=event.result,
                preview=event.preview,
                duration_ms=event.duration_ms,
                data=event.data,
                display_name=event.display_name,
            )


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
                sse = _to_sse(item)
                if sse:
                    await bus.emit(sse)
                    await asyncio.sleep(0)
    except asyncio.CancelledError:
        result = ""

    if ctx.run.cancelled:
        await bus.emit(RunCancelledEvent(run_id=ctx.run.run_id))
        return None, None

    return result, None
