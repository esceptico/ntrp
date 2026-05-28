from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntrp.knowledge import KnowledgeObject, KnowledgeObjectStatus, KnowledgeObjectType
from ntrp.memory.models import MemoryAccessEvent
from ntrp.memory.service import KnowledgeObjectService, MemoryAccessEventService


def _event(details: dict) -> MemoryAccessEvent:
    return MemoryAccessEvent(
        id=7,
        created_at=datetime.now(UTC),
        source="knowledge_activation",
        injected_fact_ids=[10],
        omitted_fact_ids=[11],
        policy_version="test",
        details=details,
    )


class _AccessEvents:
    def __init__(self, event: MemoryAccessEvent | None):
        self.event = event
        self.update_patch: dict | None = None

    async def get(self, event_id: int):
        assert event_id == 7
        return self.event

    async def update_details(self, event_id: int, patch: dict):
        assert event_id == 7
        self.update_patch = patch
        details = dict(self.event.details if self.event else {})
        details.update(patch)
        return self.event.model_copy(update={"details": details}) if self.event else None


class _Commit:
    def __init__(self):
        self.calls = 0

    async def commit(self):
        self.calls += 1


@pytest.mark.asyncio
async def test_update_outcome_marks_actual_use_only_for_visible_targets():
    event = _event(
        {
            "candidates": [
                {"object_id": "10", "activation_state": "injected", "model_visible": True},
                {"object_id": "12", "activation_state": "selected_not_injected", "model_visible": False},
            ],
            "omitted": [{"object_id": "11", "activation_state": "omitted", "model_visible": False}],
        }
    )
    access_events = _AccessEvents(event)
    commit = _Commit()
    svc = MemoryAccessEventService(SimpleNamespace(access_events=access_events, db=SimpleNamespace(conn=commit)))

    updated = await svc.update_outcome(
        event_id=7,
        outcome="corrected",
        signal="corrected",
        target_object_ids=[10, 11, 12],
    )

    assert updated is not None
    patch = access_events.update_patch
    assert patch is not None
    assert patch["actual_use_observed_target_object_ids"] == [10]
    assert patch["candidates"][0]["actual_use_observed"] is True
    assert patch["candidates"][1]["actual_use_observed"] is False
    assert patch["omitted"][0]["actual_use_observed"] is False
    assert commit.calls == 1


@pytest.mark.asyncio
async def test_update_outcome_does_not_infer_actual_use_for_task_success():
    event = _event({"candidates": [{"object_id": "10", "activation_state": "injected", "model_visible": True}]})
    access_events = _AccessEvents(event)
    commit = _Commit()
    svc = MemoryAccessEventService(SimpleNamespace(access_events=access_events, db=SimpleNamespace(conn=commit)))

    await svc.update_outcome(event_id=7, outcome="task_success", target_object_ids=[10])

    patch = access_events.update_patch
    assert patch is not None
    assert "candidates" not in patch
    assert "actual_use_observed_target_object_ids" not in patch
    assert commit.calls == 1



@pytest.mark.asyncio
async def test_update_outcome_uses_signal_when_outcome_is_generic():
    event = _event({"candidates": [{"object_id": "10", "activation_state": "injected", "model_visible": True}]})
    access_events = _AccessEvents(event)
    commit = _Commit()
    svc = MemoryAccessEventService(SimpleNamespace(access_events=access_events, db=SimpleNamespace(conn=commit)))

    await svc.update_outcome(event_id=7, signal="helpful", outcome="task_success", target_object_ids=[10])

    patch = access_events.update_patch
    assert patch is not None
    assert patch["actual_use_observed_target_object_ids"] == [10]
    assert patch["candidates"][0]["actual_use_observed"] is True

def _knowledge_object(object_id: int, metadata: dict) -> KnowledgeObject:
    return KnowledgeObject(
        id=object_id,
        object_type=KnowledgeObjectType.FACT,
        title=f"Fact {object_id}",
        text="fact text",
        status=KnowledgeObjectStatus.ACTIVE,
        scope="test",
        activation="prompt",
        proactiveness_level="L0",
        score=0.5,
        source_ids=["source:test"],
        metadata=metadata,
        created_at="2026-05-19T00:00:00+00:00",
        updated_at="2026-05-19T00:00:00+00:00",
    )


class _KnowledgeRepo:
    def __init__(self, objects: dict[int, KnowledgeObject]):
        self.objects = objects
        self.updates: dict[int, dict] = {}

    async def get_batch(self, object_ids: list[int]):
        return {object_id: self.objects[object_id] for object_id in object_ids if object_id in self.objects}

    async def update(self, object_id: int, update):
        self.updates[object_id] = update.metadata
        self.objects[object_id] = self.objects[object_id].model_copy(update={"metadata": update.metadata})
        return self.objects[object_id]


def _knowledge_service_with_repo(repo: _KnowledgeRepo) -> KnowledgeObjectService:
    svc = object.__new__(KnowledgeObjectService)
    svc._repo = repo
    return svc


@pytest.mark.asyncio
async def test_record_usage_outcome_increments_actual_use_only_for_latest_visible_activation():
    repo = _KnowledgeRepo(
        {
            10: _knowledge_object(10, {"last_activation_event_id": 42, "last_model_visible": True}),
            11: _knowledge_object(11, {"last_activation_event_id": 42, "last_model_visible": False}),
            12: _knowledge_object(12, {"last_activation_event_id": 41, "last_model_visible": True}),
        }
    )
    svc = _knowledge_service_with_repo(repo)

    await svc.record_usage_outcome(
        object_ids=[10, 11, 12],
        signal="corrected",
        outcome="corrected",
        usage_event_id=42,
        feedback_at="2026-05-25T00:00:00+00:00",
    )

    assert repo.updates[10]["actual_use_observed_count"] == 1
    assert repo.updates[10]["last_actual_use_observed"] is True
    assert "actual_use_observed_count" not in repo.updates[11]
    assert "actual_use_observed_count" not in repo.updates[12]


@pytest.mark.asyncio
async def test_record_usage_outcome_replaces_actual_use_observed_counter_idempotently():
    repo = _KnowledgeRepo(
        {
            10: _knowledge_object(
                10,
                {
                    "last_activation_event_id": 42,
                    "last_model_visible": True,
                    "actual_use_observed_count": 1,
                },
            )
        }
    )
    svc = _knowledge_service_with_repo(repo)

    await svc.record_usage_outcome(
        object_ids=[10],
        signal="irrelevant",
        outcome="irrelevant",
        usage_event_id=42,
        feedback_at="2026-05-25T00:00:00+00:00",
        previous_signal="helpful",
        previous_outcome="helpful",
        replace_existing=True,
    )

    assert repo.updates[10]["actual_use_observed_count"] == 0
    assert repo.updates[10]["last_actual_use_observed"] is False
