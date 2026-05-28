from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from ntrp.knowledge.metadata import is_lesson_promotion_candidate
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
)

_REPLACEMENT_OBJECT_TYPES = {
    KnowledgeObjectType.FACT,
    KnowledgeObjectType.LESSON,
    KnowledgeObjectType.ARTIFACT,
}


def _looks_like_review_title(title: str) -> bool:
    lowered = title.strip().casefold()
    return lowered.startswith(("review ", "revise ")) or "candidate" in lowered


def _looks_like_review_text(obj: KnowledgeObject) -> bool:
    text = obj.text.strip().casefold()
    return (
        text.startswith("review this user correction")
        or text.startswith("write gate decision:")
        or text.startswith("review whether this procedure")
    )


class KnowledgeReviewPromotionService:
    def __init__(self, *, objects, events, create_replacement: Callable[[KnowledgeObjectCreate], Awaitable[KnowledgeObject]]):
        self._objects = objects
        self._events = events
        self._create_replacement_object = create_replacement

    async def promote_if_approved(self, obj: KnowledgeObject) -> None:
        if not is_lesson_promotion_candidate(obj) or obj.status != KnowledgeObjectStatus.APPROVED:
            return
        source_id = f"knowledge:{obj.id}"
        target_ids = await self._target_ids(obj)
        existing = await self._objects.get_by_source_id(source_id)
        if existing is not None:
            for target_id in target_ids:
                await self._supersede_target(obj, target_id, existing.id)
            return

        replacement = await self._create_replacement(obj, source_id, target_ids)
        for target_id in target_ids:
            await self._supersede_target(obj, target_id, replacement.id)

    async def _create_replacement(
        self,
        obj: KnowledgeObject,
        source_id: str,
        target_ids: list[int],
    ) -> KnowledgeObject:
        target = await self._first_existing_target(target_ids)
        metadata = {
            "approved_candidate_id": obj.id,
            "promoted_from": obj.object_type.value,
            **obj.metadata,
        }
        if target_ids:
            metadata["replacement_for_object_ids"] = target_ids
        payload = KnowledgeObjectCreate(
            object_type=self._replacement_object_type(obj, target),
            title=self._replacement_title(obj),
            text=self._replacement_text(obj),
            status=KnowledgeObjectStatus.ACTIVE,
            scope=obj.scope,
            activation="prompt",
            proactiveness_level="L0",
            score=max(obj.score, 0.5),
            source_ids=[source_id, *obj.source_ids],
            metadata=metadata,
        )
        return await self._create_replacement_object(payload)

    async def _target_ids(self, obj: KnowledgeObject) -> list[int]:
        ids: list[int] = []
        for key in ("target_object_id", "target_procedure_id"):
            value = self._int_or_none(obj.metadata.get(key))
            if value is not None and value not in ids:
                ids.append(value)
        raw_target_ids = obj.metadata.get("target_memory_ids")
        if isinstance(raw_target_ids, list):
            for raw_target_id in raw_target_ids:
                value = self._int_or_none(raw_target_id)
                if value is not None and value not in ids:
                    ids.append(value)
        return ids

    async def _first_existing_target(self, target_ids: list[int]) -> KnowledgeObject | None:
        for target_id in target_ids:
            target = await self._objects.get(target_id)
            if target is not None:
                return target
        return None

    @staticmethod
    def _int_or_none(value) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _replacement_object_type(obj: KnowledgeObject, target: KnowledgeObject | None) -> KnowledgeObjectType:
        raw_candidate_type = obj.metadata.get("candidate_object_type")
        if isinstance(raw_candidate_type, str):
            try:
                candidate_type = KnowledgeObjectType(raw_candidate_type)
            except ValueError:
                candidate_type = None
            if candidate_type in _REPLACEMENT_OBJECT_TYPES:
                return candidate_type
        if target is not None and target.object_type in _REPLACEMENT_OBJECT_TYPES:
            return target.object_type
        return KnowledgeObjectType.LESSON

    @staticmethod
    def _replacement_title(obj: KnowledgeObject) -> str:
        if not _looks_like_review_title(obj.title):
            return obj.title.strip()[:500]
        raw_title = obj.metadata.get("candidate_title")
        if isinstance(raw_title, str) and raw_title.strip():
            return raw_title.strip()[:500]
        correction_text = obj.metadata.get("correction_text")
        if isinstance(correction_text, str) and correction_text.strip():
            return f"Correction: {correction_text.strip()[:480]}"[:500]
        return obj.title.replace("candidate", "lesson").replace("Candidate", "Lesson").replace("Revise", "Lesson")[:500]

    @staticmethod
    def _replacement_text(obj: KnowledgeObject) -> str:
        text = obj.text.strip()
        if text and not _looks_like_review_text(obj):
            return text
        raw_text = obj.metadata.get("candidate_text")
        if isinstance(raw_text, str) and raw_text.strip():
            return raw_text.strip()
        correction_text = obj.metadata.get("correction_text")
        if isinstance(correction_text, str) and correction_text.strip():
            return correction_text.strip()
        return text or obj.text

    async def _supersede_target(self, obj: KnowledgeObject, target_id: int, replacement_id: int) -> None:
        target = await self._objects.get(target_id)
        if target is None or target.status != KnowledgeObjectStatus.ACTIVE:
            return
        reason = "approved review candidate created replacement memory"
        await self._objects.update(
            target.id,
            KnowledgeObjectUpdate(
                status=KnowledgeObjectStatus.SUPERSEDED,
                superseded_by_object_id=replacement_id,
                superseded_at=datetime.now(UTC).isoformat(),
                supersession_reason=reason,
            ),
        )
        await self._events.create(
            actor="system",
            action="knowledge.superseded",
            target_type=target.object_type.value,
            target_id=target.id,
            reason=reason,
            policy_version="knowledge.objects.v1",
            details={"approved_candidate_id": obj.id, "replacement_object_id": replacement_id},
        )
