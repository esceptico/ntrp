from collections.abc import Callable
from datetime import UTC, datetime

from ntrp.automation.store import AutomationStore
from ntrp.constants import EXTRACTION_CONTEXT_MESSAGES
from ntrp.logging import get_logger
from ntrp.memory.chat_extraction import extract_from_chat
from ntrp.memory.facts import FactMemory
from ntrp.memory.models import SourceType

_logger = get_logger(__name__)


def create_chat_extraction_handler(memory: FactMemory, store: AutomationStore) -> Callable:
    async def handler(context: dict | None) -> str | None:
        if context and context.get("trigger_type") == "count":
            sid = context["session_id"]
            messages = tuple(context["messages"])
            await store.record_chat_extraction_activity(sid, messages, datetime.now(UTC))
            count = await _extract_session(sid, messages)
            return f"Extracted {count} facts" if count else None

        if context and context.get("trigger_type") == "idle":
            total = 0
            for sid, cursor, messages in await store.list_pending_chat_extractions():
                count = await _extract_session(sid, messages, cursor=cursor)
                if count:
                    total += count
            return f"Extracted {total} facts from pending sessions" if total else None

        return None

    async def _extract_session(sid: str, messages: tuple[dict, ...], cursor: int | None = None) -> int | None:
        cursor = await store.get_chat_extraction_cursor(sid) if cursor is None else cursor
        context_start = max(0, cursor - EXTRACTION_CONTEXT_MESSAGES)
        window = messages[context_start:]
        if not window:
            return None

        facts = await extract_from_chat(tuple(window), memory.model)
        await store.mark_chat_extraction_extracted(sid, len(messages), datetime.now(UTC))

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
