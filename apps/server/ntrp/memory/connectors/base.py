from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import aiosqlite
import numpy as np

from ntrp.logging import get_logger
from ntrp.memory.buffers_store import EpisodeBuffer, EpisodeBufferRepository, TurnUpdate
from ntrp.memory.connectors.claim_writer import AdjudicateClient, ExtractClient
from ntrp.memory.connectors.entity_linker import EntityLinkAdjudicateClient, MentionExtractClient
from ntrp.memory.connectors.episode_close import (
    DEFAULT_TRIGGERS,
    DedupAdjudicator,
    SummaryClient,
    TriggerConfig,
    evaluate_triggers,
    finalize_buffer,
)
from ntrp.memory.contradictions import ContradictionWatcher
from ntrp.memory.items_store import MemoryItemsRepository
from ntrp.memory.learnings import LearningsStore

_logger = get_logger(__name__)


class BufferingConnector:
    """Source-agnostic episode buffering.

    Subclasses translate a source event into ``(scope, content, source_ref)`` and
    call :meth:`ingest`; everything else — buffer lifecycle, boundary triggers,
    finalization, carry-forward, idle sweeping — is shared. ``source_kind`` keeps
    each source's buffers isolated; ``triggers`` lets bursty sources (email, Slack)
    diverge from interactive-chat cadence.
    """

    source_kind: str = "buffer"
    triggers: TriggerConfig = DEFAULT_TRIGGERS

    def __init__(
        self,
        *,
        items: MemoryItemsRepository,
        buffers: EpisodeBufferRepository,
        embedder: Any,
        llm_client: SummaryClient,
        dedup_client: DedupAdjudicator | None = None,
        learnings: LearningsStore | None = None,
        claim_extract_client: ExtractClient | None = None,
        claim_adjudicate_client: AdjudicateClient | None = None,
        mention_extract_client: MentionExtractClient | None = None,
        entity_link_client: EntityLinkAdjudicateClient | None = None,
        watcher: ContradictionWatcher | None = None,
    ):
        self.items = items
        self.buffers = buffers
        self.embedder = embedder
        self.llm_client = llm_client
        self.dedup_client = dedup_client
        self.learnings = learnings
        self.claim_extract_client = claim_extract_client
        self.claim_adjudicate_client = claim_adjudicate_client
        self.mention_extract_client = mention_extract_client
        self.entity_link_client = entity_link_client
        self.watcher = watcher

    async def ingest(
        self, *, scope: str, content: str, source_ref: dict, extra_source_refs: list[dict] | None = None
    ) -> None:
        if not content.strip():
            return

        turn_vec = await self.embedder.embed_one(content)
        buffer, created = await self._find_or_create_open(scope)
        turn = TurnUpdate(
            content=content,
            tokens=self._estimate_tokens(content),
            source_ref=source_ref,
            embedding=turn_vec,
            extra_source_refs=extra_source_refs or [],
        )

        if created or buffer.turn_count == 0:
            await self.buffers.apply_turn(buffer.id, turn)
            return

        should_close, reason = await self._detect_explicit_close(buffer, content)
        if not should_close:
            should_close, reason = evaluate_triggers(buffer, turn_vec, turn.tokens, datetime.now(UTC), self.triggers)

        if should_close:
            if not await self._embedding_dim_matches():
                await self.buffers.apply_turn(buffer.id, await self._turn_with_safe_embedding(buffer, turn))
                return
            next_buffer = await finalize_buffer(
                buffer=buffer,
                items=self.items,
                buffers=self.buffers,
                embedder=self.embedder,
                llm_client=self.llm_client,
                reason=reason or "boundary",
                config=self.triggers,
                dedup_client=self.dedup_client,
                learnings=self.learnings,
                claim_extract_client=self.claim_extract_client,
                claim_adjudicate_client=self.claim_adjudicate_client,
                mention_extract_client=self.mention_extract_client,
                entity_link_client=self.entity_link_client,
                watcher=self.watcher,
            )
            await self.buffers.apply_turn(next_buffer.id, turn)
            return

        await self.buffers.apply_turn(buffer.id, turn)

    async def close_idle_buffers(self) -> None:
        threshold_minutes = self.triggers.idle_gap.total_seconds() / 60
        for buffer in await self.buffers.find_idle(threshold_minutes, self.source_kind):
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
                    config=self.triggers,
                    dedup_client=self.dedup_client,
                    learnings=self.learnings,
                    claim_extract_client=self.claim_extract_client,
                    claim_adjudicate_client=self.claim_adjudicate_client,
                    mention_extract_client=self.mention_extract_client,
                    entity_link_client=self.entity_link_client,
                )
            except Exception:
                _logger.warning(
                    "Failed to close idle buffer",
                    source_kind=self.source_kind,
                    buffer_id=buffer.id,
                    exc_info=True,
                )

    async def _detect_explicit_close(self, buffer: EpisodeBuffer, content: str) -> tuple[bool, str | None]:
        """Override to honor a source-specific explicit boundary signal."""
        return False, None

    def _estimate_tokens(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4)

    async def _find_or_create_open(self, scope: str) -> tuple[EpisodeBuffer, bool]:
        buffer = await self.buffers.find_open(scope, self.source_kind)
        if buffer is not None:
            return buffer, False
        try:
            return await self.buffers.create(scope, self.source_kind), True
        except aiosqlite.IntegrityError:
            buffer = await self.buffers.find_open(scope, self.source_kind)
            if buffer is None:
                raise
            return buffer, False

    async def _turn_with_safe_embedding(self, buffer: EpisodeBuffer, turn: TurnUpdate) -> TurnUpdate:
        if buffer.running_centroid_vec is not None:
            fallback_vec = buffer.running_centroid_vec.astype(np.float32)
        else:
            expected = await self.items.embedding_dim()
            fallback_vec = np.zeros(int(expected or len(turn.embedding)), dtype=np.float32)
        return TurnUpdate(
            content=turn.content,
            tokens=turn.tokens,
            source_ref=turn.source_ref,
            embedding=fallback_vec,
            extra_source_refs=turn.extra_source_refs,
        )

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
