from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

import aiosqlite
import numpy as np

if TYPE_CHECKING:
    from datetime import timedelta

from ntrp.agent.types import CompletionResponse
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.buffers_store import BufferCarry, EpisodeBuffer, EpisodeBufferRepository, _normalize, join_turns
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.connectors._constants import (
    DEDUP_ADJUDICATE_LIMIT,
    DEDUP_RECALL_SIMILARITY,
    DEDUP_SCAN_LIMIT,
    DEDUP_SIMILARITY,
    DEDUP_WINDOW_DAYS,
    IDLE_GAP,
    OVERLAP_TURNS,
    TOKEN_BUDGET,
    TOPIC_SHIFT_THRESHOLD,
    TURN_BUDGET,
)
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository, derive_title

_logger = get_logger(__name__)


@dataclass(frozen=True)
class TriggerConfig:
    """Per-source episode-boundary cadence. Defaults are tuned for interactive chat;
    bursty sources (email, Slack) should override idle_gap / budgets."""

    turn_budget: int = TURN_BUDGET
    token_budget: int = TOKEN_BUDGET
    idle_gap: timedelta = IDLE_GAP
    topic_shift_threshold: float = TOPIC_SHIFT_THRESHOLD
    overlap_turns: int = OVERLAP_TURNS


DEFAULT_TRIGGERS = TriggerConfig()

_SKIP_SENTINEL = "NONE"

_SUMMARY_PROMPT = """Extract durable knowledge from this chat episode for future memory retrieval.

Keep only what is still useful weeks from now:
- decisions ("going with postgres", "dropping feature X")
- preferences ("don't like verbose logging", "always use dataclasses")
- people & relationships ("John handles infra")
- commitments ("need to send the report by Friday")
- durable project facts (architecture, ownership, constraints)

Ignore conversational filler, acknowledgements, status updates, troubleshooting
steps, how-to chatter, and transient/ephemeral state. Do not invent claims.

Output only the knowledge itself as plain prose or bullets. Do not add a
preamble, header, title, or label (no "DURABLE KNOWLEDGE EXTRACTED:" or similar).

If the episode contains no durable knowledge, respond with exactly: NONE

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


_DEDUP_ACTIONS = frozenset({"keep", "drop", "supersede", "merge"})

_DEDUP_PROMPT = """A new memory episode is about to be stored. Decide how it relates to existing
similar episodes already in memory, so we never store redundant duplicates but never lose information.

For each existing candidate you are given: its id, the embedding cosine to the new episode, and a
containment score (fraction of the new episode's words already present in that candidate; ~1.0 means
the new episode is fully contained in it).

Choose exactly one action:
- "keep": the new episode is genuinely new information. Store it as-is.
- "drop": the new episode adds nothing beyond an existing candidate (it is a subset/restatement).
- "supersede": the new episode is a richer/updated version of one candidate; store the new one and
  retire that candidate. Set target_id to that candidate.
- "merge": the new episode and one candidate each carry unique details that belong together; provide
  merged_content combining both into one episode, and set target_id to that candidate.

Respond with ONLY a JSON object, no prose, no code fences:
{{"action": "keep|drop|supersede|merge", "target_id": "<candidate id or null>", "merged_content": "<combined episode text or null>", "reason": "<short>"}}

New episode:
{new}

Existing candidates:
{candidates}
"""


@dataclass(frozen=True)
class DedupCandidate:
    item: MemoryItem
    cosine: float
    containment: float


@dataclass(frozen=True)
class DedupDecision:
    action: str
    target_id: str | None = None
    merged_content: str | None = None
    reason: str = ""


class DedupAdjudicator(Protocol):
    async def __call__(self, prompt: str) -> str: ...


class CompletionDedupClient:
    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0,
            max_tokens=600,
            messages=[
                {
                    "role": "system",
                    "content": "You deduplicate personal-assistant memory episodes. Reply with JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return _summary_from_response(response)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _containment(new_text: str, candidate_text: str) -> float:
    """Asymmetric overlap: fraction of the new episode's tokens present in the
    candidate. ~1.0 when the new episode is a subset of the candidate (the case a
    symmetric cosine misses under length mismatch)."""
    new_tokens = _tokenize(new_text)
    if not new_tokens:
        return 0.0
    candidate_tokens = _tokenize(candidate_text)
    return len(new_tokens & candidate_tokens) / len(new_tokens)


def _format_candidates(candidates: list[DedupCandidate]) -> str:
    return "\n".join(
        f"- id={c.item.id} cosine={c.cosine:.3f} containment={c.containment:.3f}\n  {c.item.content}"
        for c in candidates
    )


def _parse_decision(raw: str) -> DedupDecision:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return DedupDecision(action="keep", reason="parse_failed")
    action = str(data.get("action", "keep")).lower()
    if action not in _DEDUP_ACTIONS:
        action = "keep"
    target = data.get("target_id")
    merged = data.get("merged_content")
    return DedupDecision(
        action=action,
        target_id=str(target) if target else None,
        merged_content=str(merged) if merged else None,
        reason=str(data.get("reason", "")),
    )


def _legacy_decision(candidates: list[DedupCandidate]) -> DedupDecision:
    """Used when no adjudicator is wired: collapse to the old high-threshold gate."""
    for candidate in candidates:
        if candidate.cosine >= DEDUP_SIMILARITY:
            return DedupDecision(action="drop", target_id=candidate.item.id, reason="legacy_cosine")
    return DedupDecision(action="keep")


def evaluate_triggers(
    buffer: EpisodeBuffer,
    turn_vec: np.ndarray,
    turn_tokens: int,
    now,
    config: TriggerConfig = DEFAULT_TRIGGERS,
) -> tuple[bool, str | None]:
    if buffer.turn_count + 1 >= config.turn_budget:
        return True, "turn_budget"
    if buffer.tokens + turn_tokens >= config.token_budget:
        return True, "token_budget"
    if buffer.last_activity_at + config.idle_gap < now:
        return True, "idle_gap"
    if buffer.running_centroid_vec is not None:
        drop = 1.0 - float(np.dot(_normalize(turn_vec.astype(np.float32)), buffer.running_centroid_vec))
        if drop > config.topic_shift_threshold:
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
    config: TriggerConfig = DEFAULT_TRIGGERS,
    dedup_client: DedupAdjudicator | None = None,
) -> EpisodeBuffer:
    prompt = _SUMMARY_PROMPT.format(content=buffer.content_so_far)
    summary = (await llm_client(prompt)).strip()

    if not summary or summary.upper() == _SKIP_SENTINEL:
        _logger.info("Skipping episode with no durable knowledge", scope=buffer.scope, reason=reason)
        return await _close_and_carry(buffers, buffer, config)

    embedding = await embedder.embed_one(summary)
    candidates = await _recall_candidates(items, buffer.scope, summary, embedding)

    if not candidates:
        decision = DedupDecision(action="keep")
    elif dedup_client is not None:
        decision = _parse_decision(await dedup_client(_DEDUP_PROMPT.format(new=summary, candidates=_format_candidates(candidates))))
    else:
        decision = _legacy_decision(candidates)

    await _apply_decision(
        decision=decision,
        summary=summary,
        embedding=embedding,
        buffer=buffer,
        items=items,
        embedder=embedder,
        candidates=candidates,
        reason=reason,
    )
    return await _close_and_carry(buffers, buffer, config)


async def _recall_candidates(
    items: MemoryItemsRepository, scope: str, summary: str, embedding: np.ndarray
) -> list[DedupCandidate]:
    candidate_vec = _normalize(np.asarray(embedding, dtype=np.float32))
    recent = await items.list_recent_items(
        kind="episode",
        window_days=DEDUP_WINDOW_DAYS,
        limit=DEDUP_SCAN_LIMIT,
        scope=scope,
    )
    found: list[DedupCandidate] = []
    for item in recent:
        if item.embedding is None:
            continue
        cosine = float(np.dot(candidate_vec, _normalize(item.embedding.astype(np.float32))))
        if cosine >= DEDUP_RECALL_SIMILARITY:
            found.append(DedupCandidate(item=item, cosine=cosine, containment=_containment(summary, item.content)))
    found.sort(key=lambda c: c.cosine, reverse=True)
    return found[:DEDUP_ADJUDICATE_LIMIT]


def _new_episode_insert(summary: str, embedding: np.ndarray, buffer: EpisodeBuffer) -> MemoryItemInsert:
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
    return MemoryItemInsert(
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


async def _apply_decision(
    *,
    decision: DedupDecision,
    summary: str,
    embedding: np.ndarray,
    buffer: EpisodeBuffer,
    items: MemoryItemsRepository,
    embedder: Any,
    candidates: list[DedupCandidate],
    reason: str,
) -> None:
    targets = {c.item.id: c.item for c in candidates}
    target = targets.get(decision.target_id) if decision.target_id else None

    if decision.action == "drop":
        _logger.info("Dedup: dropping redundant episode", scope=buffer.scope, reason=reason, why=decision.reason)
        return

    if decision.action == "supersede" and target is not None:
        new_id = await items.insert_item(_new_episode_insert(summary, embedding, buffer), commit=False)
        await items.insert_parent_edge(new_id, target.id, "supersedes", commit=False)
        await items.update_status(target.id, "superseded", invalid_at=datetime.now(UTC), commit=True)
        _logger.info("Dedup: superseded prior episode", scope=buffer.scope, new_id=new_id, old_id=target.id)
        return

    if decision.action == "merge" and target is not None and decision.merged_content:
        merged = decision.merged_content.strip()
        merged_embedding = await embedder.embed_one(merged)
        await items.update_item(
            target.id,
            content=merged,
            title=derive_title(merged) or None,
            confidence=target.confidence,
            tags=target.tags,
            scope=target.scope,
            status="active",
            invalid_at=None,
            embedding=merged_embedding,
        )
        _logger.info("Dedup: merged episode into prior", scope=buffer.scope, target_id=target.id)
        return

    await items.insert_item(_new_episode_insert(summary, embedding, buffer))


async def _close_and_carry(
    buffers: EpisodeBufferRepository, buffer: EpisodeBuffer, config: TriggerConfig
) -> EpisodeBuffer:
    await buffers.close(buffer.id)
    carry = _overlap_carry(buffer, config.overlap_turns)
    try:
        return await buffers.create(buffer.scope, buffer.source_kind, carry=carry)
    except aiosqlite.IntegrityError:
        existing = await buffers.find_open(buffer.scope, buffer.source_kind)
        if existing is None:
            raise
        return existing


def _overlap_carry(buffer: EpisodeBuffer, overlap_turns: int = OVERLAP_TURNS) -> BufferCarry:
    turns = buffer.content_turns
    refs = buffer.source_refs_so_far
    keep = min(overlap_turns, len(refs))
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
