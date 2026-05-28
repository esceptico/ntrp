from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ntrp.knowledge import KnowledgeObject, KnowledgeObjectStatus, KnowledgeObjectType
from ntrp.memory.models import MemoryAccessEvent
from ntrp.memory.service import KnowledgeObjectService
from ntrp.server.app import app
from ntrp.server.deps import require_memory


@pytest.mark.asyncio
async def test_heavy_knowledge_response_cache_returns_snapshot_until_refresh():
    from ntrp.server.response_cache import AsyncResponseCache

    calls = 0
    cache = AsyncResponseCache(ttl_seconds=60)
    cache_key = ("test-heavy-cache", object())

    async def load():
        nonlocal calls
        calls += 1
        return {"value": calls}

    first = await cache.get_or_load(key=cache_key, refresh=False, loader=load)
    second = await cache.get_or_load(key=cache_key, refresh=False, loader=load)
    refreshed = await cache.get_or_load(key=cache_key, refresh=True, loader=load)

    assert first["value"] == 1
    assert first["cache"]["hit"] is False
    assert second["value"] == 1
    assert second["cache"]["hit"] is True
    assert refreshed["value"] == 2
    assert refreshed["cache"]["hit"] is False


@pytest.mark.asyncio
async def test_heavy_knowledge_response_cache_invalidates_by_prefix_and_scope():
    from ntrp.server.response_cache import AsyncResponseCache

    calls = 0
    cache = AsyncResponseCache(ttl_seconds=60)
    scoped_key = ("processor_health", 123, "a")
    other_scope_key = ("processor_health", 456, "a")

    async def load():
        nonlocal calls
        calls += 1
        return {"value": calls}

    await cache.get_or_load(key=scoped_key, refresh=False, loader=load)
    await cache.get_or_load(key=other_scope_key, refresh=False, loader=load)

    cache.invalidate(prefix="processor_health", scope=123)

    scoped_reload = await cache.get_or_load(key=scoped_key, refresh=False, loader=load)
    other_scope_cached = await cache.get_or_load(key=other_scope_key, refresh=False, loader=load)

    assert scoped_reload["cache"]["hit"] is False
    assert scoped_reload["value"] == 3
    assert other_scope_cached["cache"]["hit"] is True
    assert other_scope_cached["value"] == 2


@pytest.mark.asyncio
async def test_propose_skill_promotions_invalidates_workflow_cluster_cache(monkeypatch):
    from ntrp.server.routers import knowledge as knowledge_router

    cache_calls = []

    class FakeCache:
        def invalidate(self, *, prefix, scope):
            cache_calls.append((prefix, scope))

    class FakeProcessorService:
        def __init__(self, svc):
            self.svc = svc

        async def propose_skill_promotions(self, *, limit, min_successes):
            return SimpleNamespace(model_dump=lambda: {"created": 0, "scanned": 0, "skipped": 0})

    svc = object()
    monkeypatch.setattr(knowledge_router, "_HEAVY_ENDPOINT_CACHE", FakeCache())
    monkeypatch.setattr(knowledge_router, "KnowledgeProcessorService", FakeProcessorService)

    result = await knowledge_router.propose_skill_promotions(limit=10, min_successes=2, svc=svc)

    assert result == {"created": 0, "scanned": 0, "skipped": 0}
    assert cache_calls == [("workflow_clusters", id(svc))]

@pytest.mark.asyncio
async def test_review_workflow_cluster_route_invalidates_cache(monkeypatch):
    from ntrp.server.routers import knowledge as knowledge_router

    cache_calls = []

    class FakeCache:
        def invalidate(self, *, prefix, scope):
            cache_calls.append((prefix, scope))

    class FakePromotionService:
        def __init__(self, svc):
            self.svc = svc

        async def mark_workflow_cluster_review(self, cluster_id, *, status, reason=None):
            assert cluster_id == "project:ntrp:demo-workflow"
            assert status == "rejected"
            assert reason == "Noisy"
            return SimpleNamespace(model_dump=lambda: {"id": 77, "status": "rejected"})

    svc = object()
    request = knowledge_router.KnowledgeWorkflowClusterReviewRequest(status="rejected", reason="Noisy")
    monkeypatch.setattr(knowledge_router, "_HEAVY_ENDPOINT_CACHE", FakeCache())
    monkeypatch.setattr(knowledge_router, "KnowledgeSkillPromotionService", FakePromotionService)

    result = await knowledge_router.review_workflow_cluster("project:ntrp:demo-workflow", request, svc=svc)

    assert result == {"object": {"id": 77, "status": "rejected"}}
    assert cache_calls == [("workflow_clusters", id(svc))]


@pytest.mark.asyncio
async def test_create_skill_from_promotion_invalidates_workflow_cluster_cache(monkeypatch):
    from ntrp.server.routers import knowledge as knowledge_router

    cache_calls = []

    class FakeCache:
        def invalidate(self, *, prefix, scope):
            cache_calls.append((prefix, scope))

    class FakePromotionService:
        def __init__(self, svc):
            self.svc = svc

        async def create_skill_from_candidate(self, object_id, skill_service):
            return SimpleNamespace(
                metadata={"skill_created_name": "demo-skill", "skill_created_path": "/tmp/demo"},
                model_dump=lambda: {"id": object_id},
            )

    svc = object()
    monkeypatch.setattr(knowledge_router, "_HEAVY_ENDPOINT_CACHE", FakeCache())
    monkeypatch.setattr(knowledge_router, "KnowledgeSkillPromotionService", FakePromotionService)

    result = await knowledge_router.create_skill_from_promotion(42, svc=svc, skill_service=object())

    assert result == {
        "object": {"id": 42},
        "skill": {"name": "demo-skill", "path": "/tmp/demo"},
    }
    assert cache_calls == [("workflow_clusters", id(svc))]



def _access_event(
    *,
    event_id: int = 42,
    source: str = "knowledge_activation",
    details: dict | None = None,
    injected_fact_ids: list[int] | None = None,
) -> MemoryAccessEvent:
    return MemoryAccessEvent(
        id=event_id,
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
        source=source,
        query="implement closed loop",
        retrieved_fact_ids=[1, 2],
        injected_fact_ids=injected_fact_ids or [1],
        omitted_fact_ids=[2],
        bundled_fact_ids=[1],
        formatted_chars=123,
        policy_version="knowledge-v2",
        details=details
        or {
            "surface": "activation_bundle",
            "candidates": [
                {
                    "object_id": "1",
                    "surface": "prompt",
                    "selection_reason": "selected_for_prompt",
                    "used_by_model": True,
                }
            ],
        },
    )


class _MissingSourceTraceObjects:
    async def source_trace(self, object_id: int):
        raise KeyError(f"Knowledge object {object_id} not found")


class _MemoryService:
    knowledge_objects = _MissingSourceTraceObjects()


_DEFAULT_UPDATE_EVENT = object()


class _AccessEvents:
    def __init__(
        self,
        *,
        update_returns: MemoryAccessEvent | None | object = _DEFAULT_UPDATE_EVENT,
        events: list[MemoryAccessEvent] | None = None,
    ):
        self.calls = []
        self.update_calls = []
        self.update_returns = _access_event() if update_returns is _DEFAULT_UPDATE_EVENT else update_returns
        self.events = events

    async def list_recent(self, *, limit: int = 100, offset: int = 0, source: str | None = None):
        self.calls.append({"limit": limit, "offset": offset, "source": source})
        return self.events if self.events is not None else [_access_event(source=source or "manual")]

    async def get(self, event_id: int):
        if self.update_returns is None:
            return None
        return self.update_returns

    async def update_outcome(
        self,
        *,
        event_id: int,
        outcome: str,
        reason: str | None = None,
        user_corrected_answer: bool = False,
        signal: str | None = None,
        target_object_ids: list[int] | None = None,
        feedback_by_object: dict[str, object] | None = None,
    ):
        self.update_calls.append(
            {
                "event_id": event_id,
                "outcome": outcome,
                "reason": reason,
                "user_corrected_answer": user_corrected_answer,
                "signal": signal,
                "target_object_ids": target_object_ids,
                "feedback_by_object": feedback_by_object,
            }
        )
        return self.update_returns


class _KnowledgeObjects:
    def __init__(self):
        self.outcome_calls = []
        self.batch_calls = []

    async def get_batch(self, object_ids: list[int]):
        self.batch_calls.append(object_ids)
        return {
            10: SimpleNamespace(object_type=KnowledgeObjectType.FACT, status=KnowledgeObjectStatus.ACTIVE, title="Stale preference"),
            11: SimpleNamespace(object_type=KnowledgeObjectType.LESSON, status=KnowledgeObjectStatus.ACTIVE, title="Useful lesson"),
        }

    async def record_usage_outcome(
        self,
        *,
        object_ids: list[int],
        signal: str | None,
        outcome: str | None,
        usage_event_id: int | None = None,
        feedback_at: str | None = None,
        previous_signal: str | None = None,
        previous_outcome: str | None = None,
        replace_existing: bool = False,
    ):
        self.outcome_calls.append(
            {
                "object_ids": object_ids,
                "signal": signal,
                "outcome": outcome,
                "usage_event_id": usage_event_id,
                "feedback_at": feedback_at,
                "previous_signal": previous_signal,
                "previous_outcome": previous_outcome,
                "replace_existing": replace_existing,
            }
        )


class _MemoryServiceWithAccessEvents:
    def __init__(
        self,
        *,
        update_returns: MemoryAccessEvent | None | object = _DEFAULT_UPDATE_EVENT,
        events: list[MemoryAccessEvent] | None = None,
    ):
        self.access_events = _AccessEvents(update_returns=update_returns, events=events)
        self.knowledge_objects = _KnowledgeObjects()


def test_knowledge_object_sources_returns_404_for_missing_object():
    app.dependency_overrides[require_memory] = lambda: _MemoryService()
    try:
        response = TestClient(app).get("/knowledge/objects/18124/sources")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge object 18124 not found"}


def test_activation_usage_events_exposes_selection_trace():
    svc = _MemoryServiceWithAccessEvents()
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/activation/usage-events?limit=999&offset=-2")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert svc.access_events.calls == [{"limit": 500, "offset": 0, "source": "knowledge_activation"}]
    payload = response.json()
    assert payload["events"][0]["id"] == 42
    assert payload["events"][0]["details"]["candidates"][0]["selection_reason"] == "selected_for_prompt"
    assert payload["events"][0]["details"]["candidates"][0]["used_by_model"] is True


def test_activation_usage_event_outcome_updates_event_and_memory_metadata():
    svc = _MemoryServiceWithAccessEvents(update_returns=_access_event(event_id=42, injected_fact_ids=[10, 11]))
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).post(
            "/knowledge/activation/usage-events/42/outcome",
            json={
                "signal": "corrected",
                "outcome": "corrected",
                "detail": "The injected memory was stale.",
                "target_object_ids": [11, 10, 10],
            },
        )
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert len(svc.access_events.update_calls) == 1
    update_call = svc.access_events.update_calls[0]
    assert update_call["event_id"] == 42
    assert update_call["outcome"] == "corrected"
    assert update_call["reason"] == "The injected memory was stale."
    assert update_call["user_corrected_answer"] is True
    assert update_call["signal"] == "corrected"
    assert update_call["target_object_ids"] == [10, 11]
    assert sorted(update_call["feedback_by_object"].keys()) == ["10", "11"]
    assert svc.knowledge_objects.outcome_calls == [
        {
            "object_ids": [10],
            "signal": "corrected",
            "outcome": "corrected",
            "usage_event_id": 42,
            "feedback_at": update_call["feedback_by_object"]["10"]["updated_at"],
            "previous_signal": None,
            "previous_outcome": None,
            "replace_existing": False,
        },
        {
            "object_ids": [11],
            "signal": "corrected",
            "outcome": "corrected",
            "usage_event_id": 42,
            "feedback_at": update_call["feedback_by_object"]["11"]["updated_at"],
            "previous_signal": None,
            "previous_outcome": None,
            "replace_existing": False,
        },
    ]
    assert response.json()["updated_object_ids"] == [10, 11]


def test_activation_usage_event_outcome_is_idempotent_for_same_object_signal():
    event = _access_event(
        event_id=43,
        injected_fact_ids=[10],
        details={
            "feedback_by_object": {
                "10": {"signal": "helpful", "outcome": "helpful", "updated_at": "2026-05-25T00:00:00+00:00"}
            }
        },
    )
    svc = _MemoryServiceWithAccessEvents(update_returns=event)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).post(
            "/knowledge/activation/usage-events/43/outcome",
            json={"signal": "helpful", "outcome": "helpful", "target_object_ids": [10]},
        )
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert response.json()["updated_object_ids"] == []
    assert svc.knowledge_objects.outcome_calls == []
    assert len(svc.access_events.update_calls) == 1



def test_activation_usage_event_outcome_updates_detail_without_double_counting():
    event = _access_event(
        event_id=45,
        injected_fact_ids=[10],
        details={
            "feedback_by_object": {
                "10": {
                    "signal": "helpful",
                    "outcome": "helpful",
                    "detail": None,
                    "updated_at": "2026-05-25T00:00:00+00:00",
                }
            }
        },
    )
    svc = _MemoryServiceWithAccessEvents(update_returns=event)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).post(
            "/knowledge/activation/usage-events/45/outcome",
            json={
                "signal": "helpful",
                "outcome": "helpful",
                "detail": "Actually this fixed the task.",
                "target_object_ids": [10],
            },
        )
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert response.json()["updated_object_ids"] == []
    assert svc.knowledge_objects.outcome_calls == []
    assert len(svc.access_events.update_calls) == 1
    assert svc.access_events.update_calls[0]["feedback_by_object"]["10"]["detail"] == "Actually this fixed the task."

def test_activation_usage_event_outcome_reclassifies_existing_feedback_without_double_counting():
    event = _access_event(
        event_id=44,
        injected_fact_ids=[10],
        details={
            "feedback_by_object": {
                "10": {"signal": "helpful", "outcome": "helpful", "updated_at": "2026-05-25T00:00:00+00:00"}
            }
        },
    )
    svc = _MemoryServiceWithAccessEvents(update_returns=event)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).post(
            "/knowledge/activation/usage-events/44/outcome",
            json={"signal": "harmful", "outcome": "harmful", "target_object_ids": [10]},
        )
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert response.json()["updated_object_ids"] == [10]
    assert svc.knowledge_objects.outcome_calls == [
        {
            "object_ids": [10],
            "signal": "harmful",
            "outcome": "harmful",
            "usage_event_id": 44,
            "feedback_at": svc.access_events.update_calls[0]["feedback_by_object"]["10"]["updated_at"],
            "previous_signal": "helpful",
            "previous_outcome": "helpful",
            "replace_existing": True,
        }
    ]



def test_activation_usage_event_outcome_rejects_targets_outside_event():
    access_events = _AccessEvents(update_returns=_access_event())
    knowledge_objects = _KnowledgeObjects()
    svc = SimpleNamespace(access_events=access_events, knowledge_objects=knowledge_objects)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        client = TestClient(app)
        response = client.post(
            "/knowledge/activation/usage-events/42/outcome",
            json={
                "signal": "helpful",
                "outcome": "helpful",
                "target_object_ids": [999],
            },
        )
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 400
    assert response.json()["detail"]["unknown_target_object_ids"] == [999]
    assert access_events.update_calls == []
    assert knowledge_objects.outcome_calls == []

def test_activation_usage_event_outcome_returns_404_for_missing_event():
    svc = _MemoryServiceWithAccessEvents(update_returns=None)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).post(
            "/knowledge/activation/usage-events/99/outcome",
            json={"signal": "harmful", "outcome": "harmful"},
        )
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Memory access event 99 not found"}
    assert svc.knowledge_objects.outcome_calls == []


def test_activation_usage_summary_aggregates_recent_event_trace_and_outcomes():
    event = _access_event(
        event_id=43,
        injected_fact_ids=[10],
        details={
            "task": "chat_context",
            "task_id": "task-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "outcome": "harmful",
            "feedback_by_object": {
                "10": {"signal": "wrong", "outcome": "harmful", "detail": "stale", "updated_at": "2026-05-25T00:00:00+00:00"},
                "11": {"signal": "helpful", "outcome": "helpful", "detail": "useful but omitted", "updated_at": "2026-05-25T00:00:00+00:00"},
            },
            "candidates": [
                {
                    "object_id": "10",
                    "selected": True,
                    "used_by_model": True,
                    "activation_state": "injected",
                    "model_visible": True,
                    "actual_use_observed": None,
                    "selection_reason": "selected_for_prompt",
                    "surface": "prompt",
                    "rank": 1,
                    "score": 0.88,
                    "reasons": ["lexical_overlap:stale"],
                },
                {
                    "object_id": "11",
                    "selected": True,
                    "used_by_model": False,
                    "activation_state": "selected_not_injected",
                    "model_visible": False,
                    "actual_use_observed": False,
                    "selection_reason": "selected_not_injected",
                    "surface": "context",
                    "rank": 2,
                    "score": 0.42,
                    "reasons": ["under_budget"],
                },
            ],
            "omitted": [
                {
                    "object_id": "12",
                    "selected": False,
                    "used_by_model": False,
                    "activation_state": "omitted",
                    "model_visible": False,
                    "actual_use_observed": False,
                    "selection_reason": "omitted_by_budget_or_limit",
                    "surface": "context",
                    "rank": 3,
                    "score": 0.21,
                    "reasons": ["budget_exceeded"],
                }
            ],
        },
    )
    svc = _MemoryServiceWithAccessEvents(events=[event])
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/activation/usage-summary?limit=999&offset=-10")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert svc.access_events.calls == [{"limit": 500, "offset": 0, "source": "knowledge_activation"}]
    payload = response.json()
    assert payload["events_scanned"] == 1
    assert payload["policy_version"] == "knowledge.activation.usage_summary.v1"
    assert svc.knowledge_objects.batch_calls == [[1, 2, 10, 11, 12]]
    objects = {item["object_id"]: item for item in payload["objects"]}
    assert objects[10]["object_title"] == "Stale preference"
    assert objects[10]["object_type"] == "fact"
    assert objects[10]["object_status"] == "active"
    assert objects[10]["injected_count"] == 1
    assert objects[10]["selected_count"] == 1
    assert objects[10]["used_by_model_count"] == 1
    assert objects[10]["model_visible_count"] == 1
    assert objects[10]["actually_used_count"] == 0
    assert objects[10]["last_activation_rank"] == 1
    assert objects[10]["last_activation_score"] == 0.88
    assert objects[10]["last_activation_surface"] == "prompt"
    assert objects[10]["last_selection_reason"] == "selected_for_prompt"
    assert objects[10]["last_used_by_model"] is True
    assert objects[10]["last_activation_state"] == "injected"
    assert objects[10]["last_model_visible"] is True
    assert objects[10]["last_actual_use_observed"] is None
    assert objects[10]["last_activation_reasons"] == ["lexical_overlap:stale"]
    assert objects[10]["last_activation_task"] == "chat_context"
    assert objects[10]["last_activation_task_id"] == "task-1"
    assert objects[10]["last_activation_session_id"] == "session-1"
    assert objects[10]["last_activation_run_id"] == "run-1"
    assert objects[10]["outcome_counts"] == {"harmful": 1}
    assert objects[11]["outcome_counts"] == {"helpful": 1}
    assert objects[11]["selection_reasons"] == {"selected_not_injected": 1}
    assert objects[11]["last_activation_rank"] == 2
    assert objects[11]["last_selection_reason"] == "selected_not_injected"
    assert objects[11]["last_used_by_model"] is False
    assert objects[12]["selection_reasons"] == {"omitted_by_budget_or_limit": 1}
    assert objects[12]["last_activation_rank"] == 3
    assert objects[12]["last_activation_score"] == 0.21


def test_activation_usage_events_can_list_skill_activation_history():
    event = _access_event(
        event_id=77,
        source="skill_activation",
        details={
            "surface": "skill",
            "skill_name": "inspect-prod-runs",
            "skill_path": "/tmp/skills/inspect-prod-runs",
            "run_id": "run-77",
            "session_id": "session-77",
            "tool_id": "tool-77",
        },
    )
    svc = _MemoryServiceWithAccessEvents(events=[event])
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/activation/usage-events?source=skill_activation&limit=12")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert svc.access_events.calls == [{"limit": 12, "offset": 0, "source": "skill_activation"}]
    payload = response.json()
    assert payload["events"][0]["source"] == "skill_activation"
    assert payload["events"][0]["details"]["surface"] == "skill"
    assert payload["events"][0]["details"]["skill_name"] == "inspect-prod-runs"
    assert payload["events"][0]["details"]["run_id"] == "run-77"


def _knowledge_route_object(object_id: int, object_type: KnowledgeObjectType, title: str, status: KnowledgeObjectStatus = KnowledgeObjectStatus.ACTIVE) -> KnowledgeObject:
    now = datetime.now(UTC).isoformat()
    return KnowledgeObject(
        id=object_id,
        object_type=object_type,
        title=title,
        text=f"{title} body",
        status=status,
        scope="project:test",
        activation="prompt",
        proactiveness_level="L0",
        score=0.5,
        source_ids=[],
        metadata={},
        created_at=now,
        updated_at=now,
        reviewed_at=None,
    )


def test_list_knowledge_objects_route_serves_memory_library():
    class FakeKnowledgeObjects:
        def __init__(self):
            self.calls = []

        async def list(self, *, object_type=None, status=None, query=None, limit=100, offset=0):
            self.calls.append(
                {
                    "object_type": object_type,
                    "status": status,
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                }
            )
            return [_knowledge_route_object(1, KnowledgeObjectType.FACT, "Searchable fact")]

    fake_objects = FakeKnowledgeObjects()
    svc = SimpleNamespace(knowledge_objects=fake_objects)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/objects?object_type=fact&status=active&query=search&limit=25&offset=5")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    body = response.json()
    assert body["objects"][0]["title"] == "Searchable fact"
    assert fake_objects.calls == [
        {
            "object_type": KnowledgeObjectType.FACT,
            "status": KnowledgeObjectStatus.ACTIVE,
            "query": "search",
            "limit": 25,
            "offset": 5,
        }
    ]


@pytest.mark.asyncio
async def test_knowledge_object_service_list_passes_query_to_repository():
    class FakeRepo:
        def __init__(self):
            self.calls = []

        async def list(self, *, object_type=None, status=None, query=None, limit=100, offset=0):
            self.calls.append(
                {
                    "object_type": object_type,
                    "status": status,
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                }
            )
            return []

    repo = FakeRepo()
    service = KnowledgeObjectService.__new__(KnowledgeObjectService)
    service._repo = repo

    result = await service.list(
        object_type=KnowledgeObjectType.ARTIFACT,
        status=KnowledgeObjectStatus.DRAFT,
        query="needle",
        limit=250,
        offset=10,
    )

    assert result == []
    assert repo.calls == [
        {
            "object_type": KnowledgeObjectType.ARTIFACT,
            "status": KnowledgeObjectStatus.DRAFT,
            "query": "needle",
            "limit": 250,
            "offset": 10,
        }
    ]


@pytest.mark.asyncio
async def test_knowledge_object_service_summary_counts_use_repository():
    class FakeRepo:
        async def count_by_type_and_status(self):
            return {(KnowledgeObjectType.FACT, KnowledgeObjectStatus.ACTIVE): 7}

    service = KnowledgeObjectService.__new__(KnowledgeObjectService)
    service._repo = FakeRepo()

    assert await service.count_by_type_and_status() == {(KnowledgeObjectType.FACT, KnowledgeObjectStatus.ACTIVE): 7}


def test_knowledge_summary_route_serves_memory_overview():
    class FakeKnowledgeObjects:
        async def count_by_type_and_status(self):
            return {
                (KnowledgeObjectType.FACT, KnowledgeObjectStatus.ACTIVE): 3,
                (KnowledgeObjectType.FACT, KnowledgeObjectStatus.ARCHIVED): 1,
                (KnowledgeObjectType.LESSON, KnowledgeObjectStatus.ACTIVE): 2,
            }

    svc = SimpleNamespace(knowledge_objects=FakeKnowledgeObjects())
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/summary")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    surfaces = {item["object_type"]: item for item in response.json()["surfaces"]}
    assert surfaces["fact"]["count"] == 3
    assert surfaces["fact"]["counts_by_status"] == {"active": 3, "archived": 1}
    assert surfaces["lesson"]["count"] == 2


def test_list_knowledge_objects_route_uses_real_service_wrapper_query_signature():
    class FakeRepo:
        def __init__(self):
            self.calls = []

        async def list(self, *, object_type=None, status=None, query=None, limit=100, offset=0):
            self.calls.append(
                {
                    "object_type": object_type,
                    "status": status,
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                }
            )
            return [_knowledge_route_object(2, KnowledgeObjectType.ARTIFACT, "Artifact result", status=KnowledgeObjectStatus.DRAFT)]

    repo = FakeRepo()
    service = KnowledgeObjectService.__new__(KnowledgeObjectService)
    service._repo = repo
    svc = SimpleNamespace(knowledge_objects=service)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/objects?object_type=artifact&status=draft&limit=250")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    assert response.json()["objects"][0]["object_type"] == "artifact"
    assert repo.calls == [
        {
            "object_type": KnowledgeObjectType.ARTIFACT,
            "status": KnowledgeObjectStatus.DRAFT,
            "query": None,
            "limit": 250,
            "offset": 0,
        }
    ]


def test_knowledge_summary_route_uses_real_service_wrapper_counts_signature():
    class FakeRepo:
        async def count_by_type_and_status(self):
            return {(KnowledgeObjectType.ARTIFACT, KnowledgeObjectStatus.DRAFT): 4}

    service = KnowledgeObjectService.__new__(KnowledgeObjectService)
    service._repo = FakeRepo()
    svc = SimpleNamespace(knowledge_objects=service)
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/summary")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    surfaces = {item["object_type"]: item for item in response.json()["surfaces"]}
    assert surfaces["artifact"]["counts_by_status"] == {"draft": 4}


def test_knowledge_summary_route_accepts_nested_live_count_shape():
    class FakeKnowledgeObjects:
        async def count_by_type_and_status(self):
            return {
                "action_candidate": {"archived": 1, "draft": 35},
                "artifact": {"active": 91},
                "fact": {"active": 4156, "superseded": 84},
                "lesson": {"active": 58, "superseded": 16},
                "memory_episode": {"active": 214, "archived": 75},
                "procedure_candidate": {"archived": 6},
                "run_provenance": {"archived": 126},
            }

    svc = SimpleNamespace(knowledge_objects=FakeKnowledgeObjects())
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        response = TestClient(app).get("/knowledge/summary")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    surfaces = {item["object_type"]: item for item in response.json()["surfaces"]}
    assert surfaces["fact"]["count"] == 4156
    assert surfaces["fact"]["counts_by_status"] == {"active": 4156, "superseded": 84}
    assert surfaces["artifact"]["count"] == 91
    assert surfaces["memory_episode"]["counts_by_status"] == {"active": 214, "archived": 75}
    assert surfaces["outcome_feedback"]["counts_by_status"] == {}
