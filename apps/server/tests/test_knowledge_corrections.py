from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntrp.knowledge.corrections import KnowledgeCorrectionService
from ntrp.knowledge.models import KnowledgeObject, KnowledgeObjectStatus, KnowledgeObjectType


def _object(object_id: int, *, metadata: dict | None = None) -> KnowledgeObject:
    return KnowledgeObject(
        id=object_id,
        object_type=KnowledgeObjectType.FACT,
        title=f"Fact {object_id}",
        text="Old memory text",
        status=KnowledgeObjectStatus.ACTIVE,
        scope="project:ntrp",
        activation="prompt",
        proactiveness_level="L1",
        score=0.8,
        source_ids=["run:test"],
        metadata=metadata or {},
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )


class _Objects:
    def __init__(self):
        self.created = []
        self.updated = []
        self.outcome_calls = []
        self._objects = {10: _object(10)}

    async def create(self, payload):
        self.created.append(payload)
        return _object(99, metadata=payload.metadata)

    async def get(self, object_id: int):
        return self._objects.get(object_id)

    async def update(self, object_id: int, payload):
        self.updated.append((object_id, payload))
        return self._objects.get(object_id)

    async def record_usage_outcome(self, **kwargs):
        self.outcome_calls.append(kwargs)


_DEFAULT_UPDATE_RESULT = object()


class _AccessEvents:
    def __init__(self, *, update_result=_DEFAULT_UPDATE_RESULT):
        self.get_calls = []
        self.update_calls = []
        self._event = SimpleNamespace(
            id=42,
            injected_fact_ids=[11],
            details={"feedback_by_object": {"10": {"signal": "helpful", "outcome": "helpful"}}},
        )
        self.update_result = self._event if update_result is _DEFAULT_UPDATE_RESULT else update_result

    async def get(self, event_id: int):
        self.get_calls.append(event_id)
        return self._event

    async def update_outcome(self, **kwargs):
        self.update_calls.append(kwargs)
        return self.update_result


@pytest.mark.asyncio
async def test_correction_feedback_records_per_object_event_detail_and_metadata_outcome():
    objects = _Objects()
    access_events = _AccessEvents()
    service = KnowledgeCorrectionService(objects=objects, memory=SimpleNamespace(access_events=access_events))

    created = await service.apply(
        "That's wrong, remember this instead: use the new memory rule.",
        source_ids=["run:correction"],
        target_memory_ids=[10],
        usage_event_id=42,
    )

    assert created
    assert access_events.get_calls == [42]
    update_call = access_events.update_calls[0]
    assert update_call["target_object_ids"] == [10, 11]
    assert update_call["feedback_by_object"]["10"]["signal"] == "corrected"
    assert update_call["feedback_by_object"]["10"]["outcome"] == "harmful"
    assert update_call["feedback_by_object"]["11"]["signal"] == "corrected"
    assert objects.outcome_calls == [
        {
            "object_ids": [10, 11],
            "signal": "corrected",
            "outcome": "harmful",
            "usage_event_id": 42,
        }
    ]


@pytest.mark.asyncio
async def test_correction_does_not_record_usage_outcome_when_usage_event_update_fails():
    objects = _Objects()
    access_events = _AccessEvents(update_result=None)
    service = KnowledgeCorrectionService(objects=objects, memory=SimpleNamespace(access_events=access_events))

    created = await service.apply(
        "That's wrong, remember this instead: do not use the stale rule.",
        source_ids=["run:correction"],
        target_memory_ids=[10],
        usage_event_id=404,
    )

    assert created
    assert access_events.update_calls
    assert objects.outcome_calls == []
