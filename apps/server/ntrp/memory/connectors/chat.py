from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from ntrp.events.internal import RunCompleted
from ntrp.knowledge.episodes import EpisodeBoundaryClassifier
from ntrp.knowledge.models import KnowledgeObject, KnowledgeObjectStatus, KnowledgeObjectType
from ntrp.logging import get_logger
from ntrp.memory.buffers_store import EpisodeBuffer, EpisodeBufferRepository, TurnUpdate
from ntrp.memory.connectors._constants import IDLE_GAP
from ntrp.memory.connectors.episode_close import SummaryClient, evaluate_triggers, finalize_buffer
from ntrp.memory.items_store import MemoryItemsRepository

_logger = get_logger(__name__)

_SOURCE_KIND = "chat_msg"


class ChatConnector:
    def __init__(
        self,
        *,
        items: MemoryItemsRepository,
        buffers: EpisodeBufferRepository,
        embedder: Any,
        llm_client: SummaryClient,
        boundary_classifier: EpisodeBoundaryClassifier,
    ):
        self.items = items
        self.buffers = buffers
        self.embedder = embedder
        self.llm_client = llm_client
        self.boundary_classifier = boundary_classifier

    async def on_run_completed(self, event: RunCompleted) -> None:
        try:
            await self._on_run_completed(event)
        except Exception:
            _logger.warning("Chat connector failed", run_id=event.run_id, exc_info=True)

    async def close_idle_buffers(self) -> None:
        for buffer in await self.buffers.find_idle(IDLE_GAP.total_seconds() / 60):
            try:
                if not await self._embedding_dim_matches():
                    return
                await finalize_buffer(
                    buffer=buffer,
                    items=self.items,
                    buffers=self.buffers,
                    embedder=self.embedder,
                    llm_client=self.llm_client,
                    reason="idle_sweep",
                )
            except Exception:
                _logger.warning("Failed to close idle chat buffer", buffer_id=buffer.id, exc_info=True)

    async def _on_run_completed(self, event: RunCompleted) -> None:
        content = _turn_text(event)
        if not content.strip():
            return

        turn_vec = await self.embedder.embed_one(content)
        # TODO(slice 3): resolve project/session scopes from session metadata.
        scope = "user"
        buffer, created = await self._find_or_create_open(scope)
        turn = TurnUpdate(
            content=content,
            # Per-turn delta. event.usage.total_tokens is the LLM API's
            # cumulative run-total — each round-trip's prompt_tokens
            # includes the full growing context, so summing across the
            # agent's round-trips double-counts the conversation history
            # (quadratic-ish blowup, see slice-07-backlog §4).
            # completion_tokens is per-response; summed across round-trips
            # it equals the run's total assistant output, which IS the new
            # content added by this turn. Misses the user-message input
            # tokens (~5% under-count) — acceptable for budget triggers.
            tokens=max(0, event.usage.completion_tokens),
            source_ref={"kind": _SOURCE_KIND, "ref": event.run_id, "captured_at": datetime.now(UTC).isoformat()},
            embedding=turn_vec,
        )

        if created or buffer.turn_count == 0:
            await self.buffers.apply_turn(buffer.id, turn)
            return

        should_close, reason = await self._explicit_close(buffer, content)
        if not should_close:
            should_close, reason = evaluate_triggers(buffer, turn_vec, turn.tokens, datetime.now(UTC))

        if should_close:
            if not await self._embedding_dim_matches():
                return
            next_buffer = await finalize_buffer(
                buffer=buffer,
                items=self.items,
                buffers=self.buffers,
                embedder=self.embedder,
                llm_client=self.llm_client,
                reason=reason or "boundary",
            )
            await self.buffers.apply_turn(next_buffer.id, turn)
            return

        await self.buffers.apply_turn(buffer.id, turn)

    async def _find_or_create_open(self, scope: str) -> tuple[EpisodeBuffer, bool]:
        buffer = await self.buffers.find_open(scope, _SOURCE_KIND)
        if buffer is not None:
            return buffer, False
        try:
            return await self.buffers.create(scope, _SOURCE_KIND), True
        except aiosqlite.IntegrityError:
            buffer = await self.buffers.find_open(scope, _SOURCE_KIND)
            if buffer is None:
                raise
            return buffer, False

    async def _explicit_close(self, buffer: EpisodeBuffer, content: str) -> tuple[bool, str | None]:
        current_episode = KnowledgeObject(
            id=0,
            object_type=KnowledgeObjectType.MEMORY_EPISODE,
            title="Open chat episode",
            text=buffer.content_so_far,
            status=KnowledgeObjectStatus.ACTIVE,
            scope=buffer.scope,
            metadata={"episode_status": "open"},
            created_at=buffer.started_at.isoformat(),
            updated_at=buffer.last_activity_at.isoformat(),
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

    async def _embedding_dim_matches(self) -> bool:
        expected = await self.items.embedding_dim()
        actual = int(self.embedder.config.dim)
        if expected is not None and expected != actual:
            _logger.error(
                "Memory embedding dim mismatch; skipping episode close",
                expected_dim=expected,
                actual_dim=actual,
            )
            return False
        return True


def _turn_text(event: RunCompleted) -> str:
    user_text = _last_role_text(event.messages, "user")
    assistant_text = _last_role_text(event.messages, "assistant") or event.result or ""
    parts = []
    if user_text:
        parts.append(f"User: {user_text}")
    if assistant_text:
        parts.append(f"Assistant: {assistant_text}")
    return "\n".join(parts)


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
