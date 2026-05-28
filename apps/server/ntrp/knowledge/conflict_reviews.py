from __future__ import annotations

from typing import TYPE_CHECKING

from ntrp.knowledge.contradictions import SemanticConflict
from ntrp.knowledge.metadata import PROMOTION_KIND_MEMORY_WRITE_REVIEW, WRITE_GATE_VERSION
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    MemoryWriteAction,
)
from ntrp.knowledge.store import KnowledgeObjectRepository

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class KnowledgeConflictReviewService:
    def __init__(
        self,
        *,
        repo: KnowledgeObjectRepository,
        create_object: Callable[[KnowledgeObjectCreate], Awaitable[KnowledgeObject]],
    ):
        self._repo = repo
        self._create_object = create_object

    async def ensure_review(self, obj: KnowledgeObject, conflicts: list[SemanticConflict]) -> None:
        conflict_ids = list(dict.fromkeys(conflict.object_id for conflict in conflicts))
        if await self._has_review(obj.id, conflict_ids):
            return
        await self._create_object(self._review_candidate(obj, conflicts, conflict_ids))

    async def _has_review(self, obj_id: int, conflict_ids: list[int]) -> bool:
        expected_conflicts = set(conflict_ids)
        candidates = await self._repo.list_many(
            object_types={KnowledgeObjectType.ACTION_CANDIDATE},
            statuses={KnowledgeObjectStatus.DRAFT, KnowledgeObjectStatus.APPROVED},
            limit=1_000,
        )
        for candidate in candidates:
            if candidate.metadata.get("processor") != "semantic_conflict":
                continue
            try:
                target_id = int(candidate.metadata.get("target_object_id"))
            except (TypeError, ValueError):
                continue
            if target_id != obj_id:
                continue
            raw_conflicts = candidate.metadata.get("conflict_ids")
            if not isinstance(raw_conflicts, list):
                continue
            try:
                candidate_conflicts = {int(item) for item in raw_conflicts}
            except (TypeError, ValueError):
                continue
            if candidate_conflicts == expected_conflicts:
                return True
        return False

    def _review_candidate(
        self,
        obj: KnowledgeObject,
        conflicts: list[SemanticConflict],
        conflict_ids: list[int],
    ) -> KnowledgeObjectCreate:
        evidence_terms = list(dict.fromkeys(term for conflict in conflicts for term in conflict.shared_terms))
        reason = "semantic_conflict_detected"
        confidence = max(conflict.confidence for conflict in conflicts)
        source_ids = list(
            dict.fromkeys(
                [
                    f"knowledge:{obj.id}",
                    *(f"knowledge:{conflict_id}" for conflict_id in conflict_ids),
                    *obj.source_ids,
                ]
            )
        )
        return KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.ACTION_CANDIDATE,
            title=f"Review memory conflict: {obj.title}"[:500],
            text=(
                "Semantic conflict detected. Review before changing durable memory.\n\n"
                f"Candidate type: {obj.object_type.value}\n"
                f"Candidate text: {obj.text}"
            ),
            status=KnowledgeObjectStatus.DRAFT,
            scope=obj.scope,
            activation="review",
            proactiveness_level="L2",
            score=max(0.2, obj.score),
            source_ids=source_ids,
            metadata={
                "processor": "semantic_conflict",
                "promotion_kind": PROMOTION_KIND_MEMORY_WRITE_REVIEW,
                "target_object_id": obj.id,
                "conflict_ids": conflict_ids,
                "candidate_object_type": obj.object_type.value,
                "candidate_title": obj.title,
                "candidate_text": obj.text,
                "write_gate": WRITE_GATE_VERSION,
                "write_gate_action": MemoryWriteAction.REVIEW.value,
                "write_gate_reason": reason,
                "write_gate_confidence": confidence,
                "evidence_terms": evidence_terms,
            },
        )
