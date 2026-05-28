from datetime import UTC, datetime
from re import search

from ntrp.knowledge.metadata import PROCESSOR_CORRECTION_SIGNAL, PROMOTION_KIND_MEMORY_WRITE_REVIEW, WRITE_GATE_VERSION
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
)


def correction_signal_text(text: str) -> str | None:
    raw = text.strip()
    if len(raw) < 16:
        return None
    lowered = raw.casefold()
    triggers = (
        "no, i meant",
        "no i meant",
        "that's wrong",
        "that is wrong",
        "don't do that",
        "dont do that",
        "remember this instead",
        "from now on",
        "you keep",
    )
    if lowered.startswith(triggers):
        return raw
    if search(r"(?i)\b(no,\s+not that|no,\s+i meant|that's wrong|that is wrong)\b", raw):
        return raw
    return None


class KnowledgeCorrectionService:
    def __init__(self, *, objects, memory):
        self._objects = objects
        self._memory = memory

    async def apply(
        self,
        text: str,
        *,
        source_ids: list[str] | None = None,
        scope: str | None = None,
        target_memory_ids: list[int] | None = None,
        usage_event_id: int | None = None,
    ) -> list[KnowledgeObject]:
        correction_text = correction_signal_text(text)
        if correction_text is None:
            return []

        target_ids = list(dict.fromkeys(int(item) for item in target_memory_ids or []))
        all_source_ids = list(dict.fromkeys([*(source_ids or []), *(f"knowledge:{item}" for item in target_ids)]))
        if not all_source_ids:
            return []

        candidate = await self._objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.ACTION_CANDIDATE,
                title=f"Review correction: {correction_text[:120]}",
                text=f"Review this user correction and decide whether it should become a fact or lesson:\n\n{correction_text}",
                status=KnowledgeObjectStatus.DRAFT,
                scope=scope,
                activation="review",
                proactiveness_level="L2",
                score=0.6,
                source_ids=all_source_ids,
                metadata={
                    "processor": PROCESSOR_CORRECTION_SIGNAL,
                    "kind": "correction",
                    "promotion_kind": PROMOTION_KIND_MEMORY_WRITE_REVIEW,
                    "correction_text": correction_text,
                    "target_memory_ids": target_ids,
                    "usage_event_id": usage_event_id,
                    "write_gate": WRITE_GATE_VERSION,
                    "write_gate_action": "review",
                    "write_gate_reason": "user_correction_signal",
                    "write_gate_confidence": 0.82,
                },
            )
        )

        for target_id in target_ids:
            target = await self._objects.get(target_id)
            if target is None:
                continue
            metadata = dict(target.metadata)
            candidate_ids = [
                int(item)
                for item in metadata.get("correction_candidate_ids", [])
                if isinstance(item, int | str) and str(item).isdigit()
            ]
            if candidate.id not in candidate_ids:
                candidate_ids.append(candidate.id)
            counts = dict(metadata.get("feedback_counts") if isinstance(metadata.get("feedback_counts"), dict) else {})
            counts["corrected"] = int(counts.get("corrected", 0)) + 1
            metadata["feedback_counts"] = counts
            metadata["correction_candidate_ids"] = candidate_ids
            metadata["last_feedback_signal"] = "corrected"
            metadata["last_feedback_at"] = datetime.now(UTC).isoformat()
            await self._objects.update(
                target.id,
                KnowledgeObjectUpdate(score=max(0.0, target.score - 0.2), metadata=metadata),
            )

        if usage_event_id is not None:
            access_events = getattr(self._memory, "access_events", None)
            update_outcome = getattr(access_events, "update_outcome", None)
            if update_outcome is not None:
                existing_usage_event = None
                get_usage_event = getattr(access_events, "get", None)
                if get_usage_event is not None:
                    existing_usage_event = await get_usage_event(usage_event_id)

                outcome_ids = list(target_ids)
                for object_id in getattr(existing_usage_event, "injected_fact_ids", []) or []:
                    if isinstance(object_id, int) and object_id not in outcome_ids:
                        outcome_ids.append(object_id)

                feedback_by_object = None
                if outcome_ids:
                    existing_details = getattr(existing_usage_event, "details", {}) or {}
                    raw_feedback = existing_details.get("feedback_by_object") if isinstance(existing_details, dict) else None
                    feedback_by_object = dict(raw_feedback) if isinstance(raw_feedback, dict) else {}
                    feedback_updated_at = datetime.now(UTC).isoformat()
                    for object_id in outcome_ids:
                        feedback_by_object[str(object_id)] = {
                            "signal": "corrected",
                            "outcome": "harmful",
                            "detail": correction_text,
                            "updated_at": feedback_updated_at,
                        }

                usage_event = await update_outcome(
                    event_id=usage_event_id,
                    outcome="harmful",
                    reason=correction_text,
                    user_corrected_answer=True,
                    signal="corrected",
                    target_object_ids=outcome_ids or None,
                    feedback_by_object=feedback_by_object,
                )
                if usage_event is not None:
                    await self._objects.record_usage_outcome(
                        object_ids=outcome_ids,
                        signal="corrected",
                        outcome="harmful",
                        usage_event_id=usage_event_id,
                    )

        return [candidate]
