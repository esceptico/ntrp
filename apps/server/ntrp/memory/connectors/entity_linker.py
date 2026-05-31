"""Entity-linking on write.

After a claim is stored, hang it off the entity nodes it is about. For each entity
the claim mentions we (1) extract the mention text (LLM), (2) hybrid-recall existing
entity nodes in the same scope (embedding + FTS, never title-exact — so ``Regina``
recalls a stored ``Regina Lin``), and (3) let an LLM judge whether the mention links
to one existing entity, is a genuinely new entity, or is nothing to track. The
decision is always an LLM call; recall only bounds the candidate set.

Linking is non-destructive: we only write a ``claim -> entity`` ``mentions`` edge and
never rewrite an entity's profile here (profiles are the lens pass's job). When unsure
we prefer under-merging (mint a new entity) over collapsing two people into one.
On ``new`` the entity's confidence is always :func:`compute_confidence`, never a literal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ntrp.agent.types import CompletionResponse
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.learnings import LearningsStore

if TYPE_CHECKING:
    import numpy as np

_logger = get_logger(__name__)

_SKIP_SENTINEL = "NONE"
_ENTITY_RECALL_LIMIT = 10
_VALID_ACTIONS = frozenset({"LINK", "NEW", "NONE"})

_MENTIONS_PROMPT_PATH = Path(__file__).with_name("prompts") / "entity_mentions.txt"

_ADJUDICATE_PROMPT = """A new memory claim mentions some entities. For EACH mention, decide how it relates to
the entities already in memory and choose one action:
- "LINK": this mention refers to exactly ONE existing entity — give its id as "target_id".
  Linking only attaches the claim to that entity; it never rewrites the entity's profile.
- "NEW": this is a genuinely new entity not present among the candidates; mint a node for it.
- "NONE": this mention is not a durable entity worth tracking (a generic noun, the user, an attribute).

Match on identity, not just a shared word: link only when the mention and a candidate are the
same real-world thing (a candidate "Regina Lin" IS the mention "Regina" when context agrees).
When you are unsure whether a mention is the same entity as a candidate, prefer NEW over LINK —
never collapse two distinct people or things into one. Judge each candidate against its full profile.
{learnings}
Respond with ONLY a JSON array, one object per mention in order, no prose, no code fences:
[{{"action": "LINK|NEW|NONE", "target_id": "<id or null>", "reason": "<short>"}}]

Mentions:
{mentions}

Candidate entities:
{candidates}
"""


class MentionExtractClient(Protocol):
    async def __call__(self, prompt: str) -> str: ...


class EntityLinkAdjudicateClient(Protocol):
    async def __call__(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class LinkDecision:
    action: str
    target_id: str | None = None
    reason: str = ""


def _content_from_response(response: CompletionResponse | str) -> str:
    if isinstance(response, str):
        return response
    return response.choices[0].message.content if response.choices and response.choices[0].message.content else ""


class CompletionMentionExtractClient:
    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0,
            max_tokens=200,
            messages=[
                {"role": "system", "content": "Extract named entities from a personal-assistant memory claim."},
                {"role": "user", "content": prompt},
            ],
        )
        return _content_from_response(response)


class CompletionEntityLinkAdjudicateClient:
    def __init__(self, model: str):
        self.model = model

    async def __call__(self, prompt: str) -> str:
        response = await get_completion_client(self.model).completion(
            model=self.model,
            temperature=0,
            max_tokens=600,
            messages=[
                {"role": "system", "content": "You link memory claims to entity nodes. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        return _content_from_response(response)


def _parse_mentions(raw: str) -> list[str]:
    text = raw.strip()
    if not text or text.upper() == _SKIP_SENTINEL:
        return []
    mentions = [line.strip().lstrip("-*0123456789. ").strip() for line in text.splitlines()]
    return [m for m in mentions if m and m.upper() != _SKIP_SENTINEL]


def _parse_decisions(raw: str, count: int) -> list[LinkDecision]:
    """Parse the adjudicator's JSON array into one decision per mention. Fail-open to
    NEW for every mention on any parse problem or length mismatch — prefer minting a
    fresh node over silently dropping the link or merging onto the wrong entity."""
    fallback = [LinkDecision(action="NEW", reason="parse_failed") for _ in range(count)]
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
    decisions: list[LinkDecision] = []
    for entry in data:
        if not isinstance(entry, dict):
            return fallback
        action = str(entry.get("action", "NEW")).upper()
        if action not in _VALID_ACTIONS:
            action = "NEW"
        target = entry.get("target_id")
        decisions.append(
            LinkDecision(
                action=action,
                target_id=str(target) if target else None,
                reason=str(entry.get("reason", "")),
            )
        )
    return decisions


def _learnings_block(learnings: LearningsStore | None) -> str:
    if learnings is None:
        return ""
    entries = learnings.load_block("entity_link")
    if not entries:
        return ""
    return f"\nPast corrections the user made about entity linking — honor them:\n{entries}\n"


def _format_mentions(mentions: list[str]) -> str:
    return "\n".join(f"{i}. {mention}" for i, mention in enumerate(mentions))


def _format_candidates(candidates: list[MemoryItem]) -> str:
    if not candidates:
        return "(none)"
    return "\n".join(f"- id={c.id} title={c.title!r}\n  {c.content}" for c in candidates)


def _entity_confidence(claim_confidence: float) -> float:
    return compute_confidence(
        provenance="inferred",
        parent_confidences=[claim_confidence],
        contradiction_count=0,
        age_days=0,
        last_used_days=0,
        helped=0,
        hurt=0,
        ignored=0,
    )


async def link_entities(
    *,
    claim_id: str,
    claim_content: str,
    scope: str,
    items: MemoryItemsRepository,
    embedder: Any,
    mention_client: MentionExtractClient,
    adjudicate_client: EntityLinkAdjudicateClient,
    learnings: LearningsStore | None = None,
) -> list[str]:
    """Extract the entities a stored claim is about and link the claim to them.

    Returns the ids of the entity nodes the claim was attached to (existing ones it
    LINKed to plus any it minted). Writes a ``claim -> entity`` ``mentions`` edge per
    attachment; never rewrites an entity profile.
    """
    raw = await mention_client(_MENTIONS_PROMPT_PATH.read_text().format(claim=claim_content))
    mentions = _parse_mentions(raw)
    if not mentions:
        return []

    mention_embeddings = [await embedder.embed_one(mention) for mention in mentions]
    candidate_sets = [
        await items.recall_entities(query=mention, embedding=emb, scope=scope, limit=_ENTITY_RECALL_LIMIT)
        for mention, emb in zip(mentions, mention_embeddings, strict=True)
    ]

    all_candidates: dict[str, MemoryItem] = {}
    for candidate_set in candidate_sets:
        for candidate in candidate_set:
            all_candidates.setdefault(candidate.id, candidate)

    if all_candidates:
        prompt = _ADJUDICATE_PROMPT.format(
            mentions=_format_mentions(mentions),
            candidates=_format_candidates(list(all_candidates.values())),
            learnings=_learnings_block(learnings),
        )
        try:
            decisions = _parse_decisions(await adjudicate_client(prompt), len(mentions))
        except Exception:
            _logger.warning("Entity-link adjudication failed; minting new entities", scope=scope, exc_info=True)
            decisions = [LinkDecision(action="NEW", reason="adjudicate_failed") for _ in mentions]
    else:
        decisions = [LinkDecision(action="NEW", reason="no_candidates") for _ in mentions]

    linked: list[str] = []
    for mention, embedding, decision in zip(mentions, mention_embeddings, decisions, strict=True):
        if decision.action == "LINK" and decision.target_id and decision.target_id in all_candidates:
            entity_id = decision.target_id
        elif decision.action == "NONE":
            continue
        else:
            entity_id = await _mint_entity(items, claim_id, scope, mention, embedding)
        await _link_edge(items, claim_id, entity_id)
        linked.append(entity_id)
    return linked


async def _mint_entity(
    items: MemoryItemsRepository, claim_id: str, scope: str, name: str, embedding: np.ndarray
) -> str:
    claim = await items.get_item(claim_id)
    claim_confidence = claim.confidence if claim is not None else 0.5
    return await items.insert_item(
        MemoryItemInsert(
            kind="entity",
            content=name,
            title=name,
            provenance="inferred",
            source_refs=claim.source_refs if claim is not None else [],
            confidence=_entity_confidence(claim_confidence),
            status="active",
            scope=scope,
            tags=[],
            embedding=embedding,
        )
    )


async def _link_edge(items: MemoryItemsRepository, claim_id: str, entity_id: str) -> None:
    try:
        await items.insert_parent_edge(claim_id, entity_id, "mentions")
    except ValueError:
        # Self-edge / cycle guard; a claim can never legitimately be its own entity.
        _logger.warning("Skipping invalid mentions edge", claim_id=claim_id, entity_id=entity_id)
