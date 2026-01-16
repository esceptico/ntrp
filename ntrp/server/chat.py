"""Chat stream helpers."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ntrp.context import SessionData, SessionState
from ntrp.events import SSEEvent
from ntrp.memory.formatting import format_memory_context
from ntrp.server.prompts import build_system_prompt
from ntrp.server.state import RunState
from ntrp.tools.core import ApprovalResponse

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


@dataclass
class ChatContext:
    runtime: "Runtime"
    run: RunState
    session_state: SessionState
    messages: list[dict]
    user_message: str
    is_init: bool

    event_bus: asyncio.Queue[SSEEvent] = field(default_factory=asyncio.Queue)
    client_responses: asyncio.Queue[ApprovalResponse] = field(default_factory=asyncio.Queue)
    init_context: str = ""


async def resolve_session(runtime: "Runtime") -> SessionData:
    data = await runtime.restore_session()
    if not data:
        return SessionData(runtime.create_session(), [])
    return data


async def prepare_messages(
    runtime: "Runtime",
    messages: list[dict],
    user_message: str,
    last_activity: datetime | None = None,
) -> tuple[list[dict], str]:
    # Get memory context if available
    memory_context = None
    if runtime.memory:
        user_facts, recent_facts = await runtime.memory.get_context()
        memory_context = format_memory_context(user_facts, recent_facts) or None

    system_prompt = build_system_prompt(
        source_details=runtime.get_source_details(),
        last_activity=last_activity,
        memory_context=memory_context,
    )

    if not messages:
        messages = [{"role": "system", "content": system_prompt}]
    elif isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = system_prompt
    else:
        messages.insert(0, {"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": user_message})

    return messages, system_prompt
