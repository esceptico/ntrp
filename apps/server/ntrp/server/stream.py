import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from ntrp.agent import Result
from ntrp.events.sse import (
    RunCancelledEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    agent_events_to_sse,
)

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
    open_text_message_id: str | None = None
    open_text_parts: list[str] = []

    def note_text_event(event) -> None:
        nonlocal open_text_message_id, open_text_parts
        if isinstance(event, TextMessageStartEvent):
            open_text_message_id = event.message_id
            open_text_parts = []
        elif isinstance(event, TextMessageContentEvent):
            open_text_message_id = open_text_message_id or event.message_id
            open_text_parts.append(event.delta)
        elif isinstance(event, TextMessageEndEvent):
            open_text_message_id = None
            open_text_parts = []

    async def close_open_text() -> None:
        nonlocal open_text_message_id, open_text_parts
        if open_text_message_id is None:
            return
        event = TextMessageEndEvent(message_id=open_text_message_id, content="".join(open_text_parts))
        open_text_message_id = None
        open_text_parts = []
        await bus.emit(event)

    try:
        async for item in gen:
            if ctx.run.backgrounded:
                return None, gen
            if isinstance(item, Result):
                if ctx.run.cancelled:
                    break
                result = item.text
            else:
                for sse in agent_events_to_sse(item):
                    note_text_event(sse)
                    await bus.emit(sse)
                    await asyncio.sleep(0)
                if ctx.run.cancelled:
                    break
    except asyncio.CancelledError:
        await close_open_text()
        result = ""

    if ctx.run.cancelled:
        await bus.emit(RunCancelledEvent(run_id=ctx.run.run_id))
        return None, None

    return result, None
