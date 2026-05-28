from __future__ import annotations

from typing import Any, Protocol

import aiosqlite
import numpy as np

from ntrp.agent.types import CompletionResponse
from ntrp.llm.router import get_completion_client
from ntrp.memory.buffers_store import BufferCarry, EpisodeBuffer, EpisodeBufferRepository, join_turns
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.connectors._constants import IDLE_GAP, OVERLAP_TURNS, TOKEN_BUDGET, TOPIC_SHIFT_THRESHOLD, TURN_BUDGET
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository

_SUMMARY_PROMPT = """Summarize this chat episode for future memory retrieval.
Keep it factual, compact, and provenance-friendly. Do not invent preferences or claims.

Episode:
{content}
"""


class SummaryClient(Protocol):
    async def __call__(self, prompt: str) -> str: ...


class CompletionSummaryClient:
    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0,
            max_tokens=300,
            messages=[
                {"role": "system", "content": "Write concise personal-assistant memory episode summaries."},
                {"role": "user", "content": prompt},
            ],
        )
        return _summary_from_response(response)


def evaluate_triggers(
    buffer: EpisodeBuffer,
    turn_vec: np.ndarray,
    turn_tokens: int,
    now,
) -> tuple[bool, str | None]:
    if buffer.turn_count + 1 >= TURN_BUDGET:
        return True, "turn_budget"
    if buffer.tokens + turn_tokens >= TOKEN_BUDGET:
        return True, "token_budget"
    if buffer.last_activity_at + IDLE_GAP < now:
        return True, "idle_gap"
    if buffer.running_centroid_vec is not None:
        drop = 1.0 - float(np.dot(turn_vec, buffer.running_centroid_vec))
        if drop > TOPIC_SHIFT_THRESHOLD:
            return True, "topic_shift"
    return False, None


async def finalize_buffer(
    *,
    buffer: EpisodeBuffer,
    items: MemoryItemsRepository,
    buffers: EpisodeBufferRepository,
    embedder: Any,
    llm_client: SummaryClient,
    reason: str,
) -> EpisodeBuffer:
    prompt = _SUMMARY_PROMPT.format(content=buffer.content_so_far)
    summary = (await llm_client(prompt)).strip()
    if not summary:
        summary = buffer.content_so_far[:2000].strip() or "Empty chat episode"

    embedding = await embedder.embed_one(summary)
    confidence = compute_confidence(
        provenance="inferred",
        parent_confidences=[],
        contradiction_count=0,
        age_days=0,
        last_used_days=0,
        helped=0,
        hurt=0,
        ignored=0,
    )
    await items.insert_item(
        MemoryItemInsert(
            kind="episode",
            content=summary,
            provenance="inferred",
            source_refs=buffer.source_refs_so_far,
            confidence=confidence,
            status="active",
            scope=buffer.scope,
            tags=[],
            embedding=embedding,
        )
    )
    await buffers.close(buffer.id)
    carry = _overlap_carry(buffer)
    try:
        return await buffers.create(buffer.scope, buffer.source_kind, carry=carry)
    except aiosqlite.IntegrityError:
        existing = await buffers.find_open(buffer.scope, buffer.source_kind)
        if existing is None:
            raise
        return existing


def _overlap_carry(buffer: EpisodeBuffer) -> BufferCarry:
    turns = buffer.content_turns
    refs = buffer.source_refs_so_far
    keep = min(OVERLAP_TURNS, len(refs))
    carried_turns = turns[-keep:] if keep else []
    carried_refs = refs[-keep:] if keep else []
    return BufferCarry(
        content=join_turns(carried_turns),
        source_refs=carried_refs,
        # We do not store per-turn embeddings, so the previous running centroid
        # represents the whole closed buffer, not just the overlap subset. Carry
        # the textual/provenance overlap but clear centroid accounting so the
        # next buffer does not weight a stale full-buffer centroid as if it came
        # only from the overlap.
        centroid=None,
        turn_count=len(carried_refs),
        tokens=0,
    )


def _summary_from_response(response: CompletionResponse | str) -> str:
    if isinstance(response, str):
        return response
    return response.choices[0].message.content if response.choices and response.choices[0].message.content else ""
