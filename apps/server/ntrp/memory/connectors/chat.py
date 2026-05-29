from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

from ntrp.events.internal import RunCompleted
from ntrp.logging import get_logger
from ntrp.memory.buffers_store import EpisodeBuffer, EpisodeBufferRepository
from ntrp.memory.connectors.base import BufferingConnector
from ntrp.memory.connectors.episode_close import DEFAULT_TRIGGERS, DedupAdjudicator, SummaryClient
from ntrp.memory.episodes import EpisodeBoundaryClassifier, EpisodeContext
from ntrp.memory.items_store import MemoryItemsRepository

_logger = get_logger(__name__)

_SOURCE_KIND = "chat_msg"


class ChatConnector(BufferingConnector):
    source_kind = _SOURCE_KIND
    triggers = DEFAULT_TRIGGERS

    def __init__(
        self,
        *,
        items: MemoryItemsRepository,
        buffers: EpisodeBufferRepository,
        embedder: Any,
        llm_client: SummaryClient,
        boundary_classifier: EpisodeBoundaryClassifier,
        dedup_client: DedupAdjudicator | None = None,
    ):
        super().__init__(
            items=items, buffers=buffers, embedder=embedder, llm_client=llm_client, dedup_client=dedup_client
        )
        self.boundary_classifier = boundary_classifier

    async def on_run_completed(self, event: RunCompleted) -> None:
        try:
            content = _turn_text(event)
            # TODO(slice 3): resolve project/session scopes from session metadata.
            await self.ingest(
                scope="user",
                content=content,
                source_ref={
                    "kind": _SOURCE_KIND,
                    "ref": event.run_id,
                    "captured_at": datetime.now(UTC).isoformat(),
                },
                extra_source_refs=list(event.source_refs),
            )
        except Exception:
            _logger.warning("Chat connector failed", run_id=event.run_id, exc_info=True)

    async def _detect_explicit_close(self, buffer: EpisodeBuffer, content: str) -> tuple[bool, str | None]:
        current_episode = EpisodeContext(
            title="Open chat episode",
            text=buffer.content_so_far,
            metadata={"episode_status": "open"},
        )
        decision = self.boundary_classifier.decide(
            current_episode=current_episode,
            event_text=content,
            idle_seconds=int((datetime.now(UTC) - buffer.last_activity_at).total_seconds()),
        )
        if inspect.isawaitable(decision):
            decision = await decision
        explicit = bool(decision.close_current and decision.boundary_type == "explicit_switch")
        return explicit, decision.boundary_type if explicit else None


def _turn_text(event: RunCompleted) -> str:
    user_text = _last_role_text(event.messages, "user")
    if not user_text.strip():
        return ""
    return f"User: {user_text}"


def _last_role_text(messages: tuple[dict, ...], role: str) -> str:
    for message in reversed(messages):
        if str(message.get("role")) == role:
            return _content_text(message.get("content")).strip()
    return ""


def _content_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)
