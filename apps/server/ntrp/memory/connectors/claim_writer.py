"""Write-time claim extraction + LLM upsert.

After an episode is finalized, extract coarse durable claims from its summary and,
for each, let an LLM decide whether to ADD a new claim, UPDATE an existing one in
place, or do nothing (NOOP). Recall is embedding-based (cosine over same-scope
active claims); the decision is always an LLM call. Confidence is always computed
via :func:`compute_confidence`, never a literal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from ntrp.agent.types import CompletionResponse
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.buffers_store import _normalize
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.connectors._constants import (
    DEDUP_RECALL_SIMILARITY,
    DEDUP_SCAN_LIMIT,
    DEDUP_WINDOW_DAYS,
)
from ntrp.memory.contradictions import ContradictionWatcher
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.learnings import LearningsStore

_logger = get_logger(__name__)

_SKIP_SENTINEL = "NONE"
_CLAIM_RECALL_LIMIT = 10
_VALID_ACTIONS = frozenset({"ADD", "UPDATE", "NOOP"})

_EXTRACT_PROMPT_PATH = Path(__file__).with_name("prompts") / "claim_extract.txt"

_ADJUDICATE_PROMPT = """New durable claims were extracted from a just-stored memory episode. For EACH new
claim, decide how it relates to the existing claims already in memory and choose one
action:
- "ADD": this is genuinely new knowledge not captured by any existing claim.
- "UPDATE": this refines, corrects, or supersedes exactly one existing claim about the
  SAME fact — give its id as "target_id". The existing claim's text will be rewritten in
  place to the new claim.
- "NOOP": an existing claim already captures this; nothing to do.

Two claims are the SAME fact only when they describe the same subject and attribute.
Different facts about the same subject are NOT the same — never merge them. When unsure,
prefer ADD over UPDATE, and ADD over NOOP (do not lose information).
{not_same}{learnings}
Respond with ONLY a JSON array, one object per new claim in order, no prose, no code fences:
[{{"action": "ADD|UPDATE|NOOP", "target_id": "<id or null>", "reason": "<short>"}}]

New claims:
{claims}

Existing claims:
{candidates}
"""

_NOT_SAME_GUARD = (
    "\nDo not merge claims the user has marked as distinct. If two claims describe "
    "different attributes (e.g. a deadline vs. a venue), keep them as separate ADDs.\n"
)


@dataclass(frozen=True)
class ClaimCandidate:
    item: MemoryItem
    cosine: float


@dataclass(frozen=True)
class ClaimDecision:
    action: str
    target_id: str | None = None
    reason: str = ""


class ExtractClient(Protocol):
    async def __call__(self, prompt: str) -> str: ...


class AdjudicateClient(Protocol):
    async def __call__(self, prompt: str) -> str: ...


def _content_from_response(response: CompletionResponse | str) -> str:
    if isinstance(response, str):
        return response
    return response.choices[0].message.content if response.choices and response.choices[0].message.content else ""


class CompletionClaimExtractClient:
    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0,
            max_tokens=400,
            messages=[
                {"role": "system", "content": "Extract coarse, durable claims for personal-assistant memory."},
                {"role": "user", "content": prompt},
            ],
        )
        return _content_from_response(response)


class CompletionClaimAdjudicateClient:
    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0,
            max_tokens=600,
            messages=[
                {"role": "system", "content": "You upsert personal-assistant memory claims. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        return _content_from_response(response)


def _enforce_not_same(
    decisions: list[ClaimDecision],
    candidate_ids: set[str],
    learnings: LearningsStore | None,
) -> list[ClaimDecision]:
    """Hard rule (checked, not advisory): the user has recorded that certain pairs of
    claims are distinct and must never be merged. If the adjudicator nonetheless asks to
    UPDATE one member of such a pair while the other member is also a live candidate in
    this batch, demote that UPDATE to ADD so neither claim is collapsed into the other.
    Never loses information."""
    if learnings is None:
        return decisions
    pairs = learnings.load_not_same_pairs()
    if not pairs:
        return decisions
    forbidden = {
        item
        for pair in pairs
        if len(pair & candidate_ids) == 2
        for item in pair
    }
    if not forbidden:
        return decisions
    return [
        ClaimDecision(action="ADD", reason="not_same_guard")
        if d.action == "UPDATE" and d.target_id in forbidden
        else d
        for d in decisions
    ]


def _claim_confidence(parent_confidences: list[float]) -> float:
    return compute_confidence(
        provenance="inferred",
        parent_confidences=parent_confidences,
        contradiction_count=0,
        age_days=0,
        last_used_days=0,
        helped=0,
        hurt=0,
        ignored=0,
    )


def _parse_claims(raw: str) -> list[str]:
    text = raw.strip()
    if not text or text.upper() == _SKIP_SENTINEL:
        return []
    claims = [line.strip().lstrip("-*0123456789. ").strip() for line in text.splitlines()]
    return [c for c in claims if c and c.upper() != _SKIP_SENTINEL]


def _parse_decisions(raw: str, count: int) -> list[ClaimDecision]:
    """Parse the adjudicator's JSON array into one decision per claim. Fail-open to
    ADD for every claim on any parse problem or length mismatch — never lose info."""
    fallback = [ClaimDecision(action="ADD", reason="parse_failed") for _ in range(count)]
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return fallback
    if not isinstance(data, list) or len(data) != count:
        return fallback
    decisions: list[ClaimDecision] = []
    for entry in data:
        if not isinstance(entry, dict):
            return fallback
        action = str(entry.get("action", "ADD")).upper()
        if action not in _VALID_ACTIONS:
            action = "ADD"
        target = entry.get("target_id")
        decisions.append(
            ClaimDecision(
                action=action,
                target_id=str(target) if target else None,
                reason=str(entry.get("reason", "")),
            )
        )
    return decisions


async def _recall_claims(
    items: MemoryItemsRepository, scope: str, embedding: np.ndarray
) -> list[ClaimCandidate]:
    query_vec = _normalize(np.asarray(embedding, dtype=np.float32))
    recent = await items.list_recent_items(
        kind="claim",
        window_days=DEDUP_WINDOW_DAYS,
        limit=DEDUP_SCAN_LIMIT,
        scope=scope,
    )
    found: list[ClaimCandidate] = []
    for item in recent:
        if item.embedding is None:
            continue
        cosine = float(np.dot(query_vec, _normalize(item.embedding.astype(np.float32))))
        if cosine >= DEDUP_RECALL_SIMILARITY:
            found.append(ClaimCandidate(item=item, cosine=cosine))
    found.sort(key=lambda c: c.cosine, reverse=True)
    return found[:_CLAIM_RECALL_LIMIT]


def _learnings_block(learnings: LearningsStore | None) -> str:
    if learnings is None:
        return ""
    entries = learnings.load_block("dedup")
    if not entries:
        return ""
    return f"\nPast corrections the user made about merging memory — honor them:\n{entries}\n"


def _format_claims(claims: list[str]) -> str:
    return "\n".join(f"{i}. {claim}" for i, claim in enumerate(claims))


def _format_candidates(candidates: list[ClaimCandidate]) -> str:
    if not candidates:
        return "(none)"
    return "\n".join(f"- id={c.item.id}\n  {c.item.content}" for c in candidates)


async def write_claims(
    *,
    episode_id: str,
    summary: str,
    scope: str,
    items: MemoryItemsRepository,
    embedder: Any,
    extract_client: ExtractClient,
    adjudicate_client: AdjudicateClient,
    learnings: LearningsStore | None = None,
    watcher: ContradictionWatcher | None = None,
) -> list[str]:
    """Extract durable claims from a finalized episode summary and upsert them.

    Returns the ids of claims that were ADDed (UPDATE/NOOP do not yield new ids).
    """
    raw = await extract_client(_EXTRACT_PROMPT_PATH.read_text().format(summary=summary))
    claims = _parse_claims(raw)
    if not claims:
        return []

    claim_embeddings = [await embedder.embed_one(claim) for claim in claims]
    candidate_sets = [await _recall_claims(items, scope, emb) for emb in claim_embeddings]

    all_candidates: dict[str, ClaimCandidate] = {}
    for candidate_set in candidate_sets:
        for candidate in candidate_set:
            all_candidates.setdefault(candidate.item.id, candidate)

    if all_candidates:
        prompt = _ADJUDICATE_PROMPT.format(
            claims=_format_claims(claims),
            candidates=_format_candidates(list(all_candidates.values())),
            not_same=_NOT_SAME_GUARD,
            learnings=_learnings_block(learnings),
        )
        try:
            decisions = _parse_decisions(await adjudicate_client(prompt), len(claims))
        except Exception:
            _logger.warning("Claim adjudication failed; adding all claims", scope=scope, exc_info=True)
            decisions = [ClaimDecision(action="ADD", reason="adjudicate_failed") for _ in claims]
    else:
        decisions = [ClaimDecision(action="ADD", reason="no_candidates") for _ in claims]

    decisions = _enforce_not_same(decisions, set(all_candidates), learnings)

    added: list[str] = []
    for claim, embedding, decision in zip(claims, claim_embeddings, decisions, strict=True):
        if decision.action == "UPDATE" and decision.target_id and decision.target_id in all_candidates:
            await _update_claim(items, all_candidates[decision.target_id].item, episode_id, claim, embedding)
        elif decision.action == "NOOP":
            continue
        else:
            claim_id = await _add_claim(items, episode_id, scope, claim, embedding)
            added.append(claim_id)
            if watcher is not None:
                try:
                    await watcher.scan_for_new_claim(claim_id, scope=scope)
                except Exception:
                    _logger.warning("Contradiction watcher failed for new claim", scope=scope, exc_info=True)
    return added


async def _add_claim(
    items: MemoryItemsRepository, episode_id: str, scope: str, content: str, embedding: np.ndarray
) -> str:
    episode = await items.get_item(episode_id)
    parent_confidences = [episode.confidence] if episode is not None else []
    claim_id = await items.insert_item(
        MemoryItemInsert(
            kind="claim",
            content=content,
            provenance="inferred",
            source_refs=episode.source_refs if episode is not None else [],
            confidence=_claim_confidence(parent_confidences),
            status="active",
            scope=scope,
            tags=[],
            embedding=embedding,
        )
    )
    await items.insert_parent_edge(claim_id, episode_id, "evidence")
    return claim_id


async def _update_claim(
    items: MemoryItemsRepository,
    target: MemoryItem,
    episode_id: str,
    content: str,
    embedding: np.ndarray,
) -> None:
    """Refine an existing claim in place with a newly corroborating episode.

    Links the corroborating episode as fresh ``evidence`` (idempotent via
    ``INSERT OR IGNORE``) so the trust chain stays inspectable, then recomputes
    confidence from the refreshed parent set — never carries the stale literal."""
    await items.insert_parent_edge(target.id, episode_id, "evidence")
    parents = await _parent_confidences(items, target.id)
    await items.update_item(
        target.id,
        content=content,
        title=None,
        confidence=_claim_confidence(parents),
        tags=target.tags,
        scope=target.scope,
        status=target.status,
        invalid_at=target.invalid_at,
        embedding=embedding,
    )


async def _parent_confidences(items: MemoryItemsRepository, child_id: str) -> list[float]:
    confidences: list[float] = []
    for edge in await items.list_parent_edges(child_id):
        if edge.role != "evidence":
            continue
        parent = await items.get_item(edge.parent_id)
        if parent is not None:
            confidences.append(parent.confidence)
    return confidences
