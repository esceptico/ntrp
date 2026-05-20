from __future__ import annotations

from dataclasses import dataclass, field
from re import findall

from ntrp.knowledge.models import KnowledgeObject, KnowledgeObjectType

_NEGATIONS = {"not", "never", "no", "avoid", "disable", "disabled", "deny", "denied", "without", "deprecated"}
_AFFIRMATIONS = {"use", "uses", "enable", "enabled", "allow", "allowed", "with", "required", "must", "should"}
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}
_CONFLICT_PAIRS = {
    frozenset(("stable", "canary")),
    frozenset(("production", "staging")),
    frozenset(("sync", "async")),
    frozenset(("synchronous", "asynchronous")),
    frozenset(("enabled", "disabled")),
    frozenset(("enable", "disable")),
    frozenset(("allow", "deny")),
    frozenset(("allowed", "denied")),
    frozenset(("true", "false")),
    frozenset(("yes", "no")),
    frozenset(("safe", "unsafe")),
    frozenset(("current", "deprecated")),
    frozenset(("new", "old")),
}
_CONTRADICTION_TYPES = {
    KnowledgeObjectType.FACT,
    KnowledgeObjectType.LESSON,
    KnowledgeObjectType.PATTERN,
    KnowledgeObjectType.PROCEDURE,
}


@dataclass(frozen=True)
class SemanticConflict:
    object_id: int
    reason: str
    shared_terms: list[str] = field(default_factory=list)
    confidence: float = 0.0


def _terms(text: str) -> set[str]:
    return {term for term in findall(r"[a-zA-Z0-9_]+", text.lower()) if len(term) > 2 and term not in _STOPWORDS}


def _entities(obj: KnowledgeObject) -> set[str]:
    raw = obj.metadata.get("entities")
    entities = {str(item).lower() for item in raw} if isinstance(raw, list) else set()
    graph = obj.metadata.get("entity_graph")
    if isinstance(graph, dict) and isinstance(graph.get("entities"), list):
        entities |= {str(item).lower() for item in graph["entities"]}
    return entities


def _polarity(tokens: set[str]) -> int:
    neg = bool(tokens & _NEGATIONS)
    pos = bool(tokens & _AFFIRMATIONS)
    if neg and not pos:
        return -1
    if pos and not neg:
        return 1
    return 0


def _has_pair_conflict(left: set[str], right: set[str]) -> bool:
    return any(bool(pair & left) and bool(pair & right) and not pair <= left and not pair <= right for pair in _CONFLICT_PAIRS)


def semantic_conflict(candidate: KnowledgeObject, existing: KnowledgeObject) -> SemanticConflict | None:
    """Conservative local semantic contradiction detector.

    It is intentionally deterministic: compare same-type/user-facing knowledge,
    require overlapping entities or strong term overlap, then look for opposite
    polarity or known conflicting values. This catches common stale-memory bugs
    without trusting a black-box judge.
    """
    if candidate.id == existing.id:
        return None
    if candidate.object_type not in _CONTRADICTION_TYPES or existing.object_type not in _CONTRADICTION_TYPES:
        return None
    if existing.status.value in {"archived", "rejected", "superseded"}:
        return None

    left_text = f"{candidate.title} {candidate.text}"
    right_text = f"{existing.title} {existing.text}"
    left_terms = _terms(left_text)
    right_terms = _terms(right_text)
    shared_terms = sorted(left_terms & right_terms)
    left_entities = _entities(candidate)
    right_entities = _entities(existing)
    shared_entities = left_entities & right_entities

    if not shared_entities and len(shared_terms) < 3:
        return None

    left_polarity = _polarity(left_terms)
    right_polarity = _polarity(right_terms)
    if left_polarity and right_polarity and left_polarity != right_polarity:
        return SemanticConflict(
            object_id=existing.id,
            reason="opposite_polarity",
            shared_terms=shared_terms[:12],
            confidence=0.72 if shared_entities else 0.58,
        )

    if _has_pair_conflict(left_terms, right_terms):
        return SemanticConflict(
            object_id=existing.id,
            reason="conflicting_value_pair",
            shared_terms=shared_terms[:12],
            confidence=0.68 if shared_entities else 0.55,
        )

    return None


def annotate_conflicts(metadata: dict[str, object], conflicts: list[SemanticConflict]) -> dict[str, object]:
    if not conflicts:
        return metadata
    merged = dict(metadata)
    existing_ids = [int(item) for item in merged.get("contradicts_object_ids", [])] if isinstance(merged.get("contradicts_object_ids"), list) else []
    conflict_ids = list(dict.fromkeys([*existing_ids, *(conflict.object_id for conflict in conflicts)]))
    merged["contradicts_object_ids"] = conflict_ids
    merged["semantic_conflicts"] = [
        {
            "object_id": conflict.object_id,
            "reason": conflict.reason,
            "shared_terms": conflict.shared_terms,
            "confidence": conflict.confidence,
            "detector": "knowledge.contradictions.heuristic.v1",
        }
        for conflict in conflicts
    ]
    return merged
