from collections.abc import Callable

from ntrp.channel import Channel
from ntrp.constants import EXTRACTION_CONTEXT_MESSAGES
from ntrp.events.internal import RunCompleted
from ntrp.logging import get_logger
from ntrp.memory.chat_extraction import extract_from_chat
from ntrp.memory.facts import FactMemory
from ntrp.memory.models import SourceType

_logger = get_logger(__name__)


def create_chat_extraction_handler(memory: FactMemory, channel: Channel) -> Callable:
    cursors: dict[str, int] = {}
    pending: dict[str, tuple[dict, ...]] = {}

    async def on_run_completed(event: RunCompleted) -> None:
        if event.result is None or not event.messages:
            return
        pending[event.session_id] = event.messages

    channel.subscribe(RunCompleted, on_run_completed)

    async def handler(context: dict | None) -> str | None:
        if context and context.get("trigger_type") == "count":
            sid = context["session_id"]
            messages = tuple(context["messages"])
            count = await _extract_session(sid, messages)
            return f"Extracted {count} facts" if count else None

        if context and context.get("trigger_type") == "idle":
            total = 0
            for sid in list(pending):
                count = await _extract_session(sid, pending[sid])
                if count:
                    total += count
            return f"Extracted {total} facts from pending sessions" if total else None

        return None

    async def _extract_session(sid: str, messages: tuple[dict, ...]) -> int | None:
        cursor = cursors.get(sid, 0)
        context_start = max(0, cursor - EXTRACTION_CONTEXT_MESSAGES)
        window = messages[context_start:]
        if not window:
            return None

        facts = await extract_from_chat(tuple(window), memory.model)
        cursors[sid] = len(messages)
        pending.pop(sid, None)

        if not facts:
            return None

        _logger.info("Extracted %d facts from chat (session %s)", len(facts), sid[:8])
        source_ref = f"{sid}:{context_start}-{len(messages)}"
        for fact_text in facts:
            await memory.remember(
                text=fact_text,
                source_type=SourceType.CHAT,
                source_ref=source_ref,
            )
        return len(facts)

    return handler
