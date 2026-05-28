from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ntrp.knowledge.contradictions import semantic_conflict
from ntrp.knowledge.metadata import PROMOTION_KIND_MEMORY_WRITE_REVIEW, WRITE_GATE_VERSION
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    MemoryWriteAction,
    MemoryWriteDecision,
)
from ntrp.knowledge.similarity import knowledge_similarity, knowledge_tokens_from_text
from ntrp.knowledge.store import KnowledgeObjectRepository

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_DURABLE_TYPES = {KnowledgeObjectType.FACT, KnowledgeObjectType.LESSON, KnowledgeObjectType.ARTIFACT}
_CONFLICT_TYPES = {KnowledgeObjectType.FACT, KnowledgeObjectType.LESSON}
_EXTERNAL_SOURCE_PREFIXES = {
    "answer",
    "episode",
    "legacy-observation",
    "longmemeval",
    "memory_episode",
    "project",
    "run",
    "session",
    "source",
    "turn",
}
_LEGACY_WRITABLE_TYPES = {
    KnowledgeObjectType.PATTERN,
    KnowledgeObjectType.PROCEDURE,
    KnowledgeObjectType.PROCEDURE_CANDIDATE,
}
_GATED_STATUSES = {KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.DRAFT}
_EXTRACTOR_PREFIX = "episode.close."


def _metadata_with_decision(
    metadata: dict[str, object],
    *,
    action: MemoryWriteAction,
    reason: str,
    confidence: float,
    duplicate_ids: list[int] | None = None,
    conflict_ids: list[int] | None = None,
) -> dict[str, object]:
    updated = dict(metadata)
    updated["write_gate"] = WRITE_GATE_VERSION
    updated["write_gate_action"] = action.value
    updated["write_gate_reason"] = reason
    updated["write_gate_confidence"] = confidence
    if duplicate_ids is not None:
        updated["duplicate_candidate_ids"] = duplicate_ids
    if conflict_ids is not None:
        updated["conflict_ids"] = conflict_ids
    return updated


def _is_episode_extracted(payload: KnowledgeObjectCreate) -> bool:
    extractor = str(payload.metadata.get("extractor", ""))
    return payload.metadata.get("extracted_from") == "episode_close" or extractor.startswith(_EXTRACTOR_PREFIX)


def _has_episode_source(payload: KnowledgeObjectCreate) -> bool:
    if not payload.source_ids:
        return False
    if payload.metadata.get("source_episode_id") is not None:
        return True
    return any(
        source_id.startswith(("knowledge:", "episode:", "memory_episode:")) or "episode" in source_id.casefold()
        for source_id in payload.source_ids
    )


def _is_explicit_correction(payload: KnowledgeObjectCreate) -> bool:
    return payload.metadata.get("explicit_memory_command") in {"actually", "correction"}


def _parse_knowledge_source_ref(source_id: str) -> int | None:
    prefix, sep, raw_id = source_id.partition(":")
    if prefix != "knowledge" or not sep:
        return None
    try:
        return int(raw_id)
    except ValueError:
        return None


def _pseudo_object(payload: KnowledgeObjectCreate) -> KnowledgeObject:
    now = datetime.now(UTC).isoformat()
    return KnowledgeObject(
        id=-1,
        object_type=payload.object_type,
        title=payload.title,
        text=payload.text,
        status=payload.status,
        scope=payload.scope,
        activation=payload.activation,
        proactiveness_level=payload.proactiveness_level,
        score=payload.score,
        source_ids=payload.source_ids,
        metadata=payload.metadata,
        created_at=now,
        updated_at=now,
    )


class KnowledgeWriteGate:
    def __init__(self, repo: KnowledgeObjectRepository):
        self._repo = repo

    async def decide(self, payload: KnowledgeObjectCreate) -> MemoryWriteDecision:
        candidate = self._normalize_candidate(payload)

        if _is_episode_extracted(candidate) and candidate.object_type == KnowledgeObjectType.ENTITY_PROFILE:
            return MemoryWriteDecision(
                action=MemoryWriteAction.IGNORE,
                object_type=candidate.object_type,
                candidate=None,
                reason="episode_extraction_entity_profile_ignored",
                confidence=0.9,
                source_ids=candidate.source_ids,
            )

        if _is_episode_extracted(candidate) and candidate.object_type in _DURABLE_TYPES and not _has_episode_source(candidate):
            return MemoryWriteDecision(
                action=MemoryWriteAction.IGNORE,
                object_type=candidate.object_type,
                candidate=None,
                reason="episode_extraction_missing_source_episode",
                confidence=0.95,
                source_ids=candidate.source_ids,
                warnings=["durable extracted memory must cite episode provenance"],
            )

        if candidate.object_type in _DURABLE_TYPES and candidate.status in _GATED_STATUSES and not candidate.source_ids:
            reason = "durable_memory_missing_source"
            review = self._review_candidate(
                candidate,
                action=MemoryWriteAction.REVIEW,
                reason=reason,
                confidence=0.95,
            )
            return MemoryWriteDecision(
                action=MemoryWriteAction.REVIEW,
                object_type=candidate.object_type,
                candidate=review,
                reason=reason,
                confidence=0.95,
                source_ids=review.source_ids,
                warnings=["active or draft durable memory requires source provenance"],
            )

        if candidate.object_type in _DURABLE_TYPES and candidate.status in _GATED_STATUSES:
            invalid_source_refs = await self._invalid_source_refs(candidate)
            if invalid_source_refs:
                reason = "durable_memory_invalid_source_ref"
                review = self._review_candidate(
                    candidate,
                    action=MemoryWriteAction.REVIEW,
                    reason=reason,
                    confidence=0.9,
                )
                review = review.model_copy(
                    update={
                        "metadata": {
                            **review.metadata,
                            "invalid_source_refs": invalid_source_refs,
                        }
                    }
                )
                return MemoryWriteDecision(
                    action=MemoryWriteAction.REVIEW,
                    object_type=candidate.object_type,
                    candidate=review,
                    reason=reason,
                    confidence=0.9,
                    source_ids=review.source_ids,
                    warnings=["active or draft durable memory has invalid source references"],
                )

        if (
            candidate.object_type in _CONFLICT_TYPES
            and candidate.status == KnowledgeObjectStatus.ACTIVE
            and not _is_explicit_correction(candidate)
        ):
            conflict = await self._first_conflict(candidate)
            if conflict is not None:
                review = self._review_candidate(
                    candidate,
                    action=MemoryWriteAction.REVIEW,
                    reason=conflict.reason,
                    confidence=conflict.confidence,
                    target_id=conflict.object_id,
                    conflict_ids=[conflict.object_id],
                )
                return MemoryWriteDecision(
                    action=MemoryWriteAction.REVIEW,
                    object_type=candidate.object_type,
                    target_id=conflict.object_id,
                    candidate=review,
                    reason=conflict.reason,
                    confidence=conflict.confidence,
                    source_ids=review.source_ids,
                    warnings=["candidate conflicts with active memory"],
                )

            duplicate, duplicate_confidence, terms = await self._first_duplicate(candidate)
            if duplicate is not None:
                reason = "candidate_duplicates_active_memory"
                review = self._review_candidate(
                    candidate,
                    action=MemoryWriteAction.REVIEW,
                    reason=reason,
                    confidence=duplicate_confidence,
                    target_id=duplicate.id,
                    duplicate_ids=[duplicate.id],
                    evidence_terms=terms,
                )
                return MemoryWriteDecision(
                    action=MemoryWriteAction.REVIEW,
                    object_type=candidate.object_type,
                    target_id=duplicate.id,
                    candidate=review,
                    reason=reason,
                    confidence=duplicate_confidence,
                    source_ids=review.source_ids,
                    warnings=["candidate looks like a duplicate of active memory"],
                )

        reason = "accepted"
        return MemoryWriteDecision(
            action=MemoryWriteAction.WRITE,
            object_type=candidate.object_type,
            candidate=self._annotate_candidate(candidate, action=MemoryWriteAction.WRITE, reason=reason, confidence=0.85),
            reason=reason,
            confidence=0.85,
            source_ids=candidate.source_ids,
        )

    def _normalize_candidate(self, payload: KnowledgeObjectCreate) -> KnowledgeObjectCreate:
        metadata = dict(payload.metadata)
        object_type = payload.object_type
        status = payload.status
        activation = payload.activation

        if _is_episode_extracted(payload) and object_type in _LEGACY_WRITABLE_TYPES:
            metadata.setdefault("normalized_from_object_type", object_type.value)
            metadata.setdefault("requested_status", status.value)
            object_type = KnowledgeObjectType.LESSON
            status = KnowledgeObjectStatus.ACTIVE
            activation = "prompt"
        elif object_type in _LEGACY_WRITABLE_TYPES and status in _GATED_STATUSES:
            metadata.setdefault("normalized_from_object_type", object_type.value)
            metadata.setdefault("requested_status", status.value)
            if object_type == KnowledgeObjectType.PROCEDURE_CANDIDATE:
                metadata.setdefault("promotion_kind", PROMOTION_KIND_MEMORY_WRITE_REVIEW)
                object_type = KnowledgeObjectType.ACTION_CANDIDATE
                status = KnowledgeObjectStatus.DRAFT
                activation = "review"
            else:
                object_type = KnowledgeObjectType.LESSON
                activation = "prompt"

        return payload.model_copy(
            update={
                "object_type": object_type,
                "status": status,
                "activation": activation,
                "metadata": metadata,
            }
        )

    def _annotate_candidate(
        self,
        candidate: KnowledgeObjectCreate,
        *,
        action: MemoryWriteAction,
        reason: str,
        confidence: float,
    ) -> KnowledgeObjectCreate:
        if candidate.object_type == KnowledgeObjectType.ACTION_CANDIDATE and candidate.metadata.get("write_gate") == WRITE_GATE_VERSION:
            return candidate
        return candidate.model_copy(
            update={
                "metadata": _metadata_with_decision(
                    candidate.metadata,
                    action=action,
                    reason=reason,
                    confidence=confidence,
                )
            }
        )

    async def _first_conflict(self, candidate: KnowledgeObjectCreate):
        pseudo = _pseudo_object(candidate)
        existing = await self._repo.list_many(
            object_types={KnowledgeObjectType.FACT, KnowledgeObjectType.LESSON},
            statuses={KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.APPROVED},
            limit=1_000,
        )
        for other in existing:
            if candidate.scope is not None and other.scope not in {None, candidate.scope}:
                continue
            conflict = semantic_conflict(pseudo, other)
            if conflict is not None:
                return conflict
        return None

    async def _first_duplicate(self, candidate: KnowledgeObjectCreate) -> tuple[KnowledgeObject | None, float, list[str]]:
        candidate_tokens = knowledge_tokens_from_text(candidate.title, candidate.text)
        existing = await self._repo.list_many(
            object_types={candidate.object_type},
            statuses={KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.APPROVED},
            limit=1_000,
        )
        best: tuple[KnowledgeObject | None, float, list[str]] = (None, 0.0, [])
        for other in existing:
            if candidate.scope is not None and other.scope not in {None, candidate.scope}:
                continue
            confidence, terms = knowledge_similarity(candidate_tokens, knowledge_tokens_from_text(other.title, other.text))
            if set(candidate.source_ids) & set(other.source_ids):
                confidence = min(0.99, confidence + 0.04)
            if confidence > best[1]:
                best = (other, confidence, terms)
        if best[1] >= 0.86:
            return best
        return None, best[1], best[2]

    async def _invalid_source_refs(self, candidate: KnowledgeObjectCreate) -> list[str]:
        invalid: list[str] = []
        for source_id in candidate.source_ids:
            prefix, sep, raw_id = source_id.partition(":")
            if not sep or not prefix or not raw_id:
                invalid.append(source_id)
                continue
            if prefix == "knowledge":
                object_id = _parse_knowledge_source_ref(source_id)
                if object_id is None or await self._repo.get(object_id) is None:
                    invalid.append(source_id)
                continue
            if prefix not in _EXTERNAL_SOURCE_PREFIXES:
                invalid.append(source_id)
        return invalid

    def _review_candidate(
        self,
        candidate: KnowledgeObjectCreate,
        *,
        action: MemoryWriteAction,
        reason: str,
        confidence: float,
        target_id: int | None = None,
        duplicate_ids: list[int] | None = None,
        conflict_ids: list[int] | None = None,
        evidence_terms: list[str] | None = None,
    ) -> KnowledgeObjectCreate:
        metadata = _metadata_with_decision(
            candidate.metadata,
            action=action,
            reason=reason,
            confidence=confidence,
            duplicate_ids=duplicate_ids,
            conflict_ids=conflict_ids,
        )
        metadata["candidate_object_type"] = candidate.object_type.value
        metadata["candidate_title"] = candidate.title
        metadata["candidate_text"] = candidate.text
        metadata["promotion_kind"] = PROMOTION_KIND_MEMORY_WRITE_REVIEW
        if target_id is not None:
            metadata["target_object_id"] = target_id
        if evidence_terms:
            metadata["evidence_terms"] = evidence_terms
        target_sources = [f"knowledge:{target_id}"] if target_id is not None else []
        source_ids = list(dict.fromkeys([*target_sources, *candidate.source_ids]))
        return KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.ACTION_CANDIDATE,
            title=f"Review memory write: {candidate.title}"[:500],
            text=(
                f"Write gate decision: {action.value}\n"
                f"Reason: {reason}\n\n"
                f"Candidate type: {candidate.object_type.value}\n"
                f"Candidate text: {candidate.text}"
            ),
            status=KnowledgeObjectStatus.DRAFT,
            scope=candidate.scope,
            activation="review",
            proactiveness_level="L2",
            score=max(0.2, candidate.score),
            source_ids=source_ids,
            metadata=metadata,
        )


class KnowledgeWriteGateService:
    def __init__(
        self,
        gate: KnowledgeWriteGate,
        *,
        memory,
        create_object: Callable[[KnowledgeObjectCreate], Awaitable[KnowledgeObject]],
    ):
        self._gate = gate
        self._memory = memory
        self._create_object = create_object

    async def decide(self, payload: KnowledgeObjectCreate) -> MemoryWriteDecision:
        return await self._gate.decide(payload)

    async def apply(self, decision: MemoryWriteDecision) -> KnowledgeObject | None:
        if decision.action in {MemoryWriteAction.IGNORE, MemoryWriteAction.EXPIRE}:
            await self._memory.events.create(
                actor="system",
                action=f"knowledge.write_gate.{decision.action.value}",
                target_type=decision.object_type.value if decision.object_type is not None else "memory",
                target_id=None,
                reason=decision.reason,
                policy_version=WRITE_GATE_VERSION,
                details={
                    "confidence": decision.confidence,
                    "source_ids": decision.source_ids,
                    "warnings": decision.warnings,
                },
            )
            await self._memory.db.conn.commit()
            return None
        if decision.candidate is None:
            return None
        return await self._create_object(decision.candidate)
