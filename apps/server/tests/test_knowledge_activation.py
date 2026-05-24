import pytest

import ntrp.knowledge.sinks as knowledge_sinks
from ntrp.knowledge import (
    ActivationRequest,
    KnowledgeActivationService,
    KnowledgeArtifactRenderRequest,
    KnowledgeFeedbackRequest,
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeProfileSynthesisRequest,
    KnowledgePruneRequest,
    KnowledgePublishRequest,
    KnowledgeReflectRequest,
)
from ntrp.knowledge.processors import KnowledgeProcessorService
from ntrp.knowledge.store import KnowledgeObjectRepository
from ntrp.memory.search_source import MemorySearchSource
from ntrp.memory.store.base import GraphDatabase


def test_builtin_memory_automations_use_current_constructs():
    from ntrp.automation.builtins import BUILTINS
    from ntrp.automation.triggers import KnowledgeEventTrigger
    from ntrp.constants import BUILTIN_KNOWLEDGE_PROFILE_REFRESH_ID, BUILTIN_KNOWLEDGE_REFLECTION_ID

    by_id = {spec.task_id: spec for spec in BUILTINS}
    reflection = by_id[BUILTIN_KNOWLEDGE_REFLECTION_ID]
    event_triggers = [trigger for trigger in reflection.triggers if isinstance(trigger, KnowledgeEventTrigger)]
    assert event_triggers
    assert event_triggers[0].object_types == (KnowledgeObjectType.MEMORY_EPISODE.value,)

    profile_refresh = by_id[BUILTIN_KNOWLEDGE_PROFILE_REFRESH_ID]
    assert profile_refresh.handler == "knowledge_profile_refresh"
    assert profile_refresh.enabled is False
    assert profile_refresh.triggers == []
    assert profile_refresh.writable is True


class _FakeMemoryService:
    def __init__(self):
        self.access_events = _FakeAccessEvents()
        self.events = _FakeEvents()
        self.knowledge_objects = _FakeKnowledgeObjects()


class _FakeAccessEvent:
    formatted_chars = 0


class _FakeMemoryEvent:
    action = "fact.updated"


class _FakeAccessEvents:
    async def list_recent(self, *, limit: int = 100, offset: int = 0, source: str | None = None):
        return [_FakeAccessEvent()]


class _FakeEvents:
    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        target_type: str | None = None,
        target_id: int | None = None,
        action: str | None = None,
    ):
        return [_FakeMemoryEvent()]


class _FakeKnowledgeObjects:
    async def count_by_type(self) -> dict[str, int]:
        return {
            KnowledgeObjectType.MEMORY_EPISODE.value: 2,
            KnowledgeObjectType.FACT.value: 1,
            KnowledgeObjectType.LESSON.value: 1,
            KnowledgeObjectType.ARTIFACT.value: 1,
        }

    async def count_by_type_and_status(self) -> dict[str, dict[str, int]]:
        return {
            KnowledgeObjectType.MEMORY_EPISODE.value: {KnowledgeObjectStatus.ACTIVE.value: 2},
            KnowledgeObjectType.FACT.value: {KnowledgeObjectStatus.ACTIVE.value: 1},
            KnowledgeObjectType.LESSON.value: {KnowledgeObjectStatus.ACTIVE.value: 1},
            KnowledgeObjectType.ARTIFACT.value: {KnowledgeObjectStatus.ACTIVE.value: 1},
        }

    async def list(self, *, object_type=None, status=None, limit: int = 100, offset: int = 0):
        return await self.list_many(limit=limit, offset=offset)

    async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
        objects = [
            KnowledgeObject(
                id=1,
                object_type=KnowledgeObjectType.PATTERN,
                title="Alerting work prefers structured DB metadata",
                text="Dex automation alerts should use structured DB metadata.",
                status=KnowledgeObjectStatus.ACTIVE,
                scope="dex",
                activation="prompt",
                proactiveness_level="L0",
                score=0.6,
                source_ids=["source:pattern-1"],
                metadata={},
                created_at="2026-05-19T00:00:00+00:00",
                updated_at="2026-05-19T00:00:00+00:00",
            ),
            KnowledgeObject(
                id=2,
                object_type=KnowledgeObjectType.FACT,
                title="Dex automation alerts",
                text="Dex automation alerts should use structured metadata.",
                status=KnowledgeObjectStatus.ACTIVE,
                scope="dex",
                activation="prompt",
                proactiveness_level="L0",
                score=0.4,
                source_ids=["source:fact-1"],
                metadata={},
                created_at="2026-05-19T00:00:00+00:00",
                updated_at="2026-05-19T00:00:00+00:00",
            ),
            KnowledgeObject(
                id=3,
                object_type=KnowledgeObjectType.EVIDENCE_REF,
                title="Evidence for dex automation alerts",
                text="Raw source pointer for dex automation alerts.",
                status=KnowledgeObjectStatus.ACTIVE,
                scope="dex",
                activation="audit",
                proactiveness_level="L0",
                score=1.0,
                source_ids=["run:raw"],
                metadata={},
                created_at="2026-05-19T00:00:00+00:00",
                updated_at="2026-05-19T00:00:00+00:00",
            ),
            KnowledgeObject(
                id=4,
                object_type=KnowledgeObjectType.LESSON,
                title="Dex automation alert links",
                text="Dex automation alert links should be treated as user-facing UX defects.",
                status=KnowledgeObjectStatus.ACTIVE,
                scope="dex",
                activation="prompt",
                proactiveness_level="L0",
                score=0.4,
                source_ids=["episode:1"],
                metadata={},
                created_at="2026-05-19T00:00:00+00:00",
                updated_at="2026-05-19T00:00:00+00:00",
            ),
            KnowledgeObject(
                id=5,
                object_type=KnowledgeObjectType.FACT,
                title="Expired dex automation fact",
                text="Dex automation alerts should use the obsolete link format.",
                status=KnowledgeObjectStatus.ACTIVE,
                scope="dex",
                activation="prompt",
                proactiveness_level="L0",
                score=0.9,
                source_ids=["source:expired-fact"],
                metadata={"expires_at": "2020-01-01T00:00:00+00:00"},
                created_at="2020-01-01T00:00:00+00:00",
                updated_at="2020-01-01T00:00:00+00:00",
            ),
            KnowledgeObject(
                id=6,
                object_type=KnowledgeObjectType.ENTITY_PROFILE,
                title="Profile: Dex automation alerts",
                text="Dex automation alert profile: user cares about reliable, inspectable alert routing.",
                status=KnowledgeObjectStatus.ACTIVE,
                scope="dex",
                activation="prompt",
                proactiveness_level="L0",
                score=0.55,
                source_ids=["knowledge:1", "source:pattern-1"],
                metadata={"profile_entity": "Dex automation alerts", "memory_tier": "profile"},
                created_at="2026-05-19T00:00:00+00:00",
                updated_at="2026-05-19T00:00:00+00:00",
            ),
        ]
        if object_types:
            objects = [obj for obj in objects if obj.object_type in object_types]
        if statuses:
            objects = [obj for obj in objects if obj.status in statuses]
        return objects[offset : offset + limit]


@pytest.mark.asyncio
async def test_activation_projects_current_memory_into_typed_candidates():
    service = KnowledgeActivationService(_FakeMemoryService())  # type: ignore[arg-type]

    bundle = await service.inspect(ActivationRequest(query="dex automation alerts", budget_chars=2_000))

    assert bundle.policy_version == "knowledge.activation.v1"
    assert bundle.candidates[0].object_type == KnowledgeObjectType.PATTERN
    assert {candidate.object_type for candidate in bundle.candidates} >= {
        KnowledgeObjectType.FACT,
        KnowledgeObjectType.LESSON,
    }
    assert bundle.candidates[0].reasons == ["lexical_match", "type_weight:pattern", "status:active", "source_support"]
    assert bundle.candidates[0].signals[2].name == "evidence_strength"
    assert bundle.used_chars > 0
    assert bundle.prompt_context
    assert "Activated knowledge:" in bundle.prompt_context
    assert any(candidate.object_type == KnowledgeObjectType.LESSON for candidate in bundle.candidates)
    assert KnowledgeObjectType.EVIDENCE_REF not in {candidate.object_type for candidate in bundle.candidates}
    assert all(candidate.object_id != "5" for candidate in bundle.candidates)
    assert any(signal.name == "temporal_validity" for candidate in bundle.candidates for signal in candidate.signals)
    assert KnowledgeObjectType.ENTITY_PROFILE not in {candidate.object_type for candidate in bundle.candidates}


@pytest.mark.asyncio
async def test_activation_uses_profile_tier_for_state_queries_only():
    service = KnowledgeActivationService(_FakeMemoryService())  # type: ignore[arg-type]

    direct = await service.inspect(ActivationRequest(query="dex automation alerts", budget_chars=2_000))
    state = await service.inspect(ActivationRequest(query="what do we know about dex automation alerts", budget_chars=2_000))

    assert KnowledgeObjectType.ENTITY_PROFILE not in {candidate.object_type for candidate in direct.candidates}
    profile = next(candidate for candidate in state.candidates if candidate.object_type == KnowledgeObjectType.ENTITY_PROFILE)
    assert "profile_tier_match" in profile.reasons
    assert "query_reformulation:profile" in profile.reasons
    assert profile.source_ids


@pytest.mark.asyncio
async def test_direct_personal_memory_question_uses_episode_fallback():
    class _Objects:
        async def search_text(self, query, *, object_types=None, statuses=None, limit: int = 100):
            objects = [
                KnowledgeObject(
                    id=20,
                    object_type=KnowledgeObjectType.MEMORY_EPISODE,
                    title="Graduation session",
                    text="user: I graduated with a degree in Business Administration before moving cities.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="personal",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.0,
                    source_ids=["answer_degree"],
                    metadata={"episode_status": "closed"},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                )
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[:limit]

        async def search_entities(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

        async def search_temporal(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

    class _Memory(_FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.knowledge_objects = _Objects()

    service = KnowledgeActivationService(_Memory())  # type: ignore[arg-type]

    bundle = await service.inspect(ActivationRequest(query="What degree did I graduate with?", scope="personal"))

    assert bundle.candidates
    assert bundle.candidates[0].object_type == KnowledgeObjectType.MEMORY_EPISODE
    assert "query_reformulation:personal_memory" in bundle.candidates[0].reasons


@pytest.mark.asyncio
async def test_conversational_recall_query_uses_episode_fallback():
    class _Objects:
        async def search_text(self, query, *, object_types=None, statuses=None, limit: int = 100):
            objects = [
                KnowledgeObject(
                    id=21,
                    object_type=KnowledgeObjectType.MEMORY_EPISODE,
                    title="Restaurant recommendation session",
                    text="assistant: The romantic Italian restaurant in Rome I recommended for dinner was Roscioli.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="personal",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.0,
                    source_ids=["answer_restaurant"],
                    metadata={"episode_status": "closed"},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                )
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[:limit]

        async def search_entities(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

        async def search_temporal(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

    class _Memory(_FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.knowledge_objects = _Objects()

    service = KnowledgeActivationService(_Memory())  # type: ignore[arg-type]

    bundle = await service.inspect(
        ActivationRequest(
            query="Can you remind me of the name of the romantic Italian restaurant in Rome you recommended?",
            scope="personal",
        )
    )

    assert bundle.candidates
    assert bundle.candidates[0].object_type == KnowledgeObjectType.MEMORY_EPISODE
    assert "query_reformulation:personal_memory" in bundle.candidates[0].reasons


@pytest.mark.asyncio
async def test_personalized_recommendation_query_uses_memory_fallback():
    class _Objects:
        async def search_text(self, query, *, object_types=None, statuses=None, limit: int = 100):
            objects = [
                KnowledgeObject(
                    id=22,
                    object_type=KnowledgeObjectType.MEMORY_EPISODE,
                    title="Photography setup session",
                    text="user: My current photography setup is a Sony mirrorless camera with a 35mm prime lens.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="personal",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.0,
                    source_ids=["answer_photography"],
                    metadata={"episode_status": "closed"},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                )
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[:limit]

        async def search_entities(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

        async def search_temporal(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

    class _Memory(_FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.knowledge_objects = _Objects()

    service = KnowledgeActivationService(_Memory())  # type: ignore[arg-type]

    bundle = await service.inspect(
        ActivationRequest(
            query="Can you suggest some accessories that would complement my current photography setup?",
            scope="personal",
        )
    )

    assert bundle.candidates
    assert bundle.candidates[0].object_type == KnowledgeObjectType.MEMORY_EPISODE
    assert "query_reformulation:personal_memory" in bundle.candidates[0].reasons


@pytest.mark.asyncio
async def test_temporal_sequence_query_uses_episode_fallback():
    class _Objects:
        async def search_text(self, query, *, object_types=None, statuses=None, limit: int = 100):
            objects = [
                KnowledgeObject(
                    id=23,
                    object_type=KnowledgeObjectType.MEMORY_EPISODE,
                    title="Garden sequence session",
                    text="user: The tomatoes were started before the marigolds in the seed trays.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="personal",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.0,
                    source_ids=["answer_garden"],
                    metadata={"episode_status": "closed"},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                )
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[:limit]

        async def search_entities(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

        async def search_temporal(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

    class _Memory(_FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.knowledge_objects = _Objects()

    service = KnowledgeActivationService(_Memory())  # type: ignore[arg-type]

    bundle = await service.inspect(
        ActivationRequest(query="Which seeds were started first, the tomatoes or the marigolds?", scope="personal")
    )

    assert bundle.candidates
    assert bundle.candidates[0].object_type == KnowledgeObjectType.MEMORY_EPISODE
    assert "query_reformulation:temporal_memory" in bundle.candidates[0].reasons


@pytest.mark.asyncio
async def test_personal_yes_no_question_uses_episode_fallback():
    class _Objects:
        async def search_text(self, query, *, object_types=None, statuses=None, limit: int = 100):
            objects = [
                KnowledgeObject(
                    id=24,
                    object_type=KnowledgeObjectType.MEMORY_EPISODE,
                    title="Family grocery method session",
                    text="user: My mom is using the same grocery list method as me now.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="personal",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.0,
                    source_ids=["answer_grocery"],
                    metadata={"episode_status": "closed"},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                )
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[:limit]

        async def search_entities(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

        async def search_temporal(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

    class _Memory(_FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.knowledge_objects = _Objects()

    service = KnowledgeActivationService(_Memory())  # type: ignore[arg-type]

    bundle = await service.inspect(ActivationRequest(query="Is my mom using the same grocery list method as me?", scope="personal"))

    assert bundle.candidates
    assert bundle.candidates[0].object_type == KnowledgeObjectType.MEMORY_EPISODE
    assert "query_reformulation:personal_memory" in bundle.candidates[0].reasons


@pytest.mark.asyncio
async def test_activation_adds_review_action_for_artifact_queries():
    service = KnowledgeActivationService(_FakeMemoryService())  # type: ignore[arg-type]

    bundle = await service.inspect(ActivationRequest(query="make an obsidian note from this", budget_chars=2_000))

    actions = [
        candidate for candidate in bundle.candidates if candidate.object_type == KnowledgeObjectType.ACTION_CANDIDATE
    ]
    assert len(actions) == 1
    assert actions[0].activation == "review"
    assert actions[0].proactiveness_level == "L2"


@pytest.mark.asyncio
async def test_activation_omits_near_duplicates_with_same_source():
    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            return [
                KnowledgeObject(
                    id=10,
                    object_type=KnowledgeObjectType.PATTERN,
                    title="Dex alert metadata",
                    text="Dex alerting should use structured metadata for links.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="dex",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.5,
                    source_ids=["episode:alert"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
                KnowledgeObject(
                    id=11,
                    object_type=KnowledgeObjectType.FACT,
                    title="Dex alert metadata fact",
                    text="Dex alerting should use structured metadata for links.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="dex",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.45,
                    source_ids=["episode:alert"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
            ]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()
    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="dex alert metadata", scope="dex", budget_chars=2_000)
    )

    assert [candidate.object_id for candidate in bundle.candidates] == ["10"]
    assert [candidate.object_id for candidate in bundle.omitted] == ["11"]
    assert "diversity:near_duplicate" in bundle.omitted[0].reasons


@pytest.mark.asyncio
async def test_session_scoped_activation_allows_relevant_non_session_memory():
    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            objects = [
                KnowledgeObject(
                    id=20,
                    object_type=KnowledgeObjectType.FACT,
                    title="Durable project memory",
                    text="The user's project is dex.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="note",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.4,
                    source_ids=["source:durable"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
                KnowledgeObject(
                    id=21,
                    object_type=KnowledgeObjectType.FACT,
                    title="Session project memory",
                    text="The dex project session context is dashboard debugging.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="session:s1",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.4,
                    source_ids=["source:session"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[offset : offset + limit]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()

    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="dex project", scope="session:s1", budget_chars=2_000)
    )

    assert [candidate.object_id for candidate in bundle.candidates] == ["21", "20"]
    assert bundle.prompt_context
    assert "The user's project is dex" in bundle.prompt_context
    assert "scope_mismatch_allowed" in bundle.candidates[1].reasons


@pytest.mark.asyncio
async def test_project_scoped_activation_excludes_other_projects():
    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            objects = [
                KnowledgeObject(
                    id=22,
                    object_type=KnowledgeObjectType.FACT,
                    title="Current project deploy",
                    text="The deploy checklist uses the ntrp worker.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="project:ntrp",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.4,
                    source_ids=["source:ntrp"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
                KnowledgeObject(
                    id=23,
                    object_type=KnowledgeObjectType.FACT,
                    title="Other project deploy",
                    text="The deploy checklist uses the dex worker.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="project:dex",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.9,
                    source_ids=["source:dex"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[offset : offset + limit]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()

    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="deploy checklist", scope="project:ntrp", budget_chars=2_000)
    )

    assert [candidate.object_id for candidate in bundle.candidates] == ["22"]
    assert bundle.prompt_context
    assert "dex worker" not in bundle.prompt_context


@pytest.mark.asyncio
async def test_activation_prefers_repository_search_text():
    class _Objects(_FakeKnowledgeObjects):
        async def search_text(self, query: str, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            assert query == "rare durable project"
            return [
                KnowledgeObject(
                    id=40,
                    object_type=KnowledgeObjectType.FACT,
                    title="Rare durable project",
                    text="The rare durable project memory should come from indexed search.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="note",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.4,
                    source_ids=["source:indexed"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                )
            ]

        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            raise AssertionError("activation should use indexed search_text when available")

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()

    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="rare durable project", scope="session:s1", budget_chars=2_000)
    )

    assert [candidate.object_id for candidate in bundle.candidates] == ["40"]
    assert bundle.prompt_context


@pytest.mark.asyncio
async def test_activation_honors_request_limit():
    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            labels = ["alpha zebra", "bravo yak", "charlie xray", "delta wolf", "echo vulture"]
            objects = [
                KnowledgeObject(
                    id=30 + index,
                    object_type=KnowledgeObjectType.FACT,
                    title=f"Dex automation {label}",
                    text=f"Dex automation memory {label} should be considered.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="note",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.4,
                    source_ids=[f"source:{label}"],
                    metadata={},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                )
                for index, label in enumerate(labels)
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[offset : offset + limit]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()

    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="dex automation", limit=2, budget_chars=20_000)
    )

    assert len(bundle.candidates) == 2
    assert {candidate.object_id for candidate in bundle.omitted} == {"32", "33", "34"}
    assert all("limit_exceeded" in candidate.reasons for candidate in bundle.omitted)


@pytest.mark.asyncio
async def test_summary_exposes_draft_ui_surfaces_and_next_actions():
    service = KnowledgeActivationService(_FakeMemoryService())  # type: ignore[arg-type]

    summary = await service.summary()

    assert [surface.name for surface in summary.surfaces] == [
        "Memory episodes",
        "Facts",
        "Lessons",
        "Artifacts",
    ]
    counts = {surface.object_type: surface.count for surface in summary.surfaces}
    assert counts[KnowledgeObjectType.MEMORY_EPISODE] == 2
    assert counts[KnowledgeObjectType.FACT] == 1
    assert counts[KnowledgeObjectType.LESSON] == 1
    assert counts[KnowledgeObjectType.ARTIFACT] == 1
    status_counts = {surface.object_type: surface.counts_by_status for surface in summary.surfaces}
    assert status_counts[KnowledgeObjectType.MEMORY_EPISODE][KnowledgeObjectStatus.ACTIVE] == 2
    assert status_counts[KnowledgeObjectType.FACT][KnowledgeObjectStatus.ACTIVE] == 1
    assert status_counts[KnowledgeObjectType.LESSON][KnowledgeObjectStatus.ACTIVE] == 1
    assert status_counts[KnowledgeObjectType.ARTIFACT][KnowledgeObjectStatus.ACTIVE] == 1
    assert {action.title for action in summary.next_actions} == {
        "Reflect recent memory episodes",
        "Review manual knowledge edits",
    }


@pytest.mark.asyncio
async def test_knowledge_object_repository_persists_reviewable_objects(db: GraphDatabase):
    repo = KnowledgeObjectRepository(db.conn)

    created = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
            title="Check prod run first",
            text="When the user asks to inspect a run, check the real run before static reasoning.",
            scope="dex",
            activation="review",
            proactiveness_level="L2",
            source_ids=["episode:prod-run"],
        )
    )

    assert created.id > 0
    assert created.status == KnowledgeObjectStatus.DRAFT
    assert created.source_ids == ["episode:prod-run"]

    updated = await repo.update(created.id, KnowledgeObjectUpdate(status=KnowledgeObjectStatus.APPROVED))
    assert updated.status == KnowledgeObjectStatus.APPROVED
    assert updated.reviewed_at is not None

    listed = await repo.list(object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE)
    assert [obj.id for obj in listed] == [created.id]


@pytest.mark.asyncio
async def test_knowledge_object_repository_searches_canonical_fts(db: GraphDatabase):
    repo = KnowledgeObjectRepository(db.conn)
    unrelated = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Unrelated note",
            text="Generic filler memory about another project.",
            status=KnowledgeObjectStatus.ACTIVE,
            scope="note",
        )
    )
    target = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Rare indexed memory",
            text="needle_rare_token_zzzz belongs to the durable memory index.",
            status=KnowledgeObjectStatus.ACTIVE,
            scope="note",
        )
    )

    matches = await repo.search_text(
        "needle_rare_token_zzzz",
        object_types={KnowledgeObjectType.FACT},
        statuses={KnowledgeObjectStatus.ACTIVE},
        limit=10,
    )

    assert [match.id for match in matches] == [target.id]
    assert unrelated.id not in {match.id for match in matches}

    await repo.update(target.id, KnowledgeObjectUpdate(text="The rare token was removed from this memory."))
    matches_after_update = await repo.search_text(
        "needle_rare_token_zzzz",
        object_types={KnowledgeObjectType.FACT},
        statuses={KnowledgeObjectStatus.ACTIVE},
        limit=10,
    )
    assert matches_after_update == []


@pytest.mark.asyncio
async def test_memory_search_source_indexes_knowledge_objects(db: GraphDatabase):
    repo = KnowledgeObjectRepository(db.conn)
    created = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.LESSON,
            title="Check real runs first",
            text="When debugging automation, inspect persisted run data before static reasoning.",
            status=KnowledgeObjectStatus.ACTIVE,
            scope="dex",
            source_ids=["run:1"],
        )
    )

    items = await MemorySearchSource(db).scan()

    assert len(items) == 1
    assert items[0].source == "memory"
    assert items[0].source_id == f"knowledge:{created.id}"
    assert items[0].metadata == {
        "object_type": "lesson",
        "status": "active",
        "scope": "dex",
    }
    assert "Scope: dex" in items[0].content


@pytest.mark.asyncio
async def test_processors_reflect_render_publish_and_feedback(db: GraphDatabase, tmp_path, monkeypatch):
    from ntrp.memory.service import KnowledgeObjectService

    monkeypatch.setattr(knowledge_sinks, "NTRP_DIR", tmp_path)

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    episode = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.MEMORY_EPISODE,
            title="Episode: failed note task workflow",
            text="Result: failed and should create a note task",
            status=KnowledgeObjectStatus.ACTIVE,
            scope="session:s1",
            source_ids=["run:run-1"],
            metadata={"episode_status": "closed"},
        )
    )

    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]
    reflected = await processors.reflect(KnowledgeReflectRequest(limit=10))
    types = {obj.object_type for obj in reflected.created}
    assert KnowledgeObjectType.FACT not in types
    assert KnowledgeObjectType.LESSON not in types
    assert KnowledgeObjectType.PATTERN not in types
    assert KnowledgeObjectType.PROCEDURE_CANDIDATE not in types
    assert KnowledgeObjectType.ACTION_CANDIDATE not in types

    artifact = await processors.render_artifact(
        KnowledgeArtifactRenderRequest(
            title="Run Notes",
            object_ids=[episode.id],
        )
    )
    assert artifact.object_type == KnowledgeObjectType.ARTIFACT

    receipt = await processors.publish(
        KnowledgePublishRequest(
            artifact_id=artifact.id,
            sink="obsidian",
            sink_ref="notes/run-notes.md",
        )
    )
    assert receipt.object_type == KnowledgeObjectType.SINK_RECEIPT
    assert receipt.metadata["path"]
    assert (tmp_path / "knowledge-sinks" / "obsidian" / "run-notes.md").exists()

    feedback = await processors.feedback(
        KnowledgeFeedbackRequest(
            target_object_id=episode.id,
            signal="helpful",
            score_delta=0.2,
        )
    )
    assert feedback.object_type == KnowledgeObjectType.OUTCOME_FEEDBACK

    sources = await service.knowledge_objects.source_trace(artifact.id)
    assert sources.object.id == artifact.id
    assert sources.sources[0].object.id == episode.id

    procedure_candidate = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
            title="Procedure candidate from explicit review",
            text="When a note task workflow fails, review whether future behavior should change.",
            status=KnowledgeObjectStatus.DRAFT,
            scope="session:s1",
            source_ids=[f"knowledge:{episode.id}"],
            metadata={"processor": "manual_review", "episode_id": episode.id},
        )
    )
    updated = await service.knowledge_objects.update(
        procedure_candidate.id,
        KnowledgeObjectUpdate(status=KnowledgeObjectStatus.APPROVED),
    )
    assert updated.status == KnowledgeObjectStatus.APPROVED
    lessons = await service.knowledge_objects.list(object_type=KnowledgeObjectType.LESSON)
    assert len(lessons) == 1
    assert lessons[0].metadata["approved_candidate_id"] == procedure_candidate.id

    pruned = await processors.prune_retention(KnowledgePruneRequest(older_than_days=1, apply=True))
    assert pruned.policy_version == "knowledge.retention.v1"


@pytest.mark.asyncio
async def test_negative_procedure_feedback_creates_revision_candidate_and_supersedes_old_procedure(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]

    procedure = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE,
            title="Check prod run first",
            text="Inspect the real run before static reasoning.",
            status=KnowledgeObjectStatus.ACTIVE,
            scope="dex",
            source_ids=["episode:1"],
        )
    )

    await processors.feedback(
        KnowledgeFeedbackRequest(
            target_object_id=procedure.id,
            signal="corrected",
            detail="The procedure missed the DB row check.",
            score_delta=-0.2,
        )
    )

    candidates = await service.knowledge_objects.list(object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE)
    assert len(candidates) == 1
    assert candidates[0].metadata["target_procedure_id"] == procedure.id

    await service.knowledge_objects.update(candidates[0].id, KnowledgeObjectUpdate(status=KnowledgeObjectStatus.APPROVED))
    old = await service.knowledge_objects.get(procedure.id)
    procedures = await service.knowledge_objects.list(object_type=KnowledgeObjectType.PROCEDURE)
    lessons = await service.knowledge_objects.list(object_type=KnowledgeObjectType.LESSON)
    assert old is not None
    assert old.status == KnowledgeObjectStatus.SUPERSEDED
    assert len([item for item in procedures if item.status == KnowledgeObjectStatus.ACTIVE]) == 0
    assert len([item for item in lessons if item.status == KnowledgeObjectStatus.ACTIVE]) == 1
    assert lessons[0].metadata["target_procedure_id"] == procedure.id


@pytest.mark.asyncio
async def test_health_counts_missing_provenance_stale_and_review_queue(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]

    await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Stale fact",
            text="A stale fact with no provenance.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"verified_at": "2020-01-01T00:00:00+00:00", "stale_after_days": 1},
        )
    )
    await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.ACTION_CANDIDATE,
            title="Review action",
            text="Needs review.",
            status=KnowledgeObjectStatus.DRAFT,
            activation="review",
            proactiveness_level="L2",
            source_ids=["episode:1"],
        )
    )

    health = await processors.health()
    assert health.stale == 1
    assert health.missing_provenance == 1
    assert health.review_queue == 1


@pytest.mark.asyncio
async def test_knowledge_object_service_dispatches_create_and_update_events(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    events = []

    async def dispatch(event):
        events.append(event)

    service.set_event_dispatcher(dispatch)

    obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.MEMORY_EPISODE,
            title="Episode: useful memory event",
            text="Result: useful memory event.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["run:run-1"],
        )
    )
    await service.update(obj.id, KnowledgeObjectUpdate(status=KnowledgeObjectStatus.ARCHIVED))

    assert [event.action for event in events] == ["created", "updated"]
    assert events[0].object_type == "memory_episode"
    assert events[1].status == "archived"


@pytest.mark.asyncio
async def test_memory_episode_groups_multiple_turns_and_runs(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    episode = await service.create_memory_episode(
        session_id="sess-1",
        title="Episode: implement memory architecture",
        summary="The user and assistant documented and implemented memory naming semantics.",
        turn_ids=["turn-1", "turn-2"],
        run_ids=["run-1"],
    )
    episode = await service.append_memory_episode_sources(episode.id, turn_ids=["turn-3"], run_ids=["run-2"])
    assert episode is not None
    closed = await service.close_memory_episode(
        episode.id,
        outcome="Implemented and tested.",
        boundary_reason="artifact_delivered",
        boundary_confidence=0.86,
        extracted_memory_ids=[101, 101, 102],
    )

    assert closed is not None
    assert closed.object_type == KnowledgeObjectType.MEMORY_EPISODE
    assert closed.metadata["memory_role"] == "memory_episode"
    assert closed.metadata["episode_status"] == "closed"
    assert closed.metadata["source_turn_ids"] == ["turn-1", "turn-2", "turn-3"]
    assert closed.metadata["source_run_ids"] == ["run-1", "run-2"]
    assert closed.metadata["extracted_memory_ids"] == [101, 102]
    assert "turn:turn-3" in closed.source_ids
    assert "run:run-2" in closed.source_ids


@pytest.mark.asyncio
async def test_assimilate_run_completed_groups_runs_and_respects_boundaries(db: GraphDatabase):
    from ntrp.agent import Usage
    from ntrp.events.internal import RunCompleted
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    first, first_decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-1",
            session_id="sess-1",
            messages=({"role": "user", "content": "work on memory architecture"},),
            usage=Usage(),
            result="Started memory architecture implementation.",
        )
    )
    second, second_decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-2",
            session_id="sess-1",
            messages=({"role": "user", "content": "continue memory architecture"},),
            usage=Usage(),
            result="Added tests for memory architecture.",
        )
    )

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first_decision.open_new is True
    assert second_decision.continue_current is True
    assert second.metadata["source_run_ids"] == ["run-1", "run-2"]

    closed, close_decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-3",
            session_id="sess-1",
            messages=({"role": "assistant", "content": "implemented and tests pass"},),
            usage=Usage(),
            result="Implemented and tests pass.",
        )
    )

    assert closed is not None
    assert close_decision.close_current is True
    assert closed.metadata["episode_status"] == "closed"
    assert closed.metadata["source_run_ids"] == ["run-1", "run-2", "run-3"]


@pytest.mark.asyncio
async def test_assimilate_run_completed_excludes_tool_results_from_episode_text(db: GraphDatabase):
    from ntrp.agent import Usage
    from ntrp.events.internal import RunCompleted
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    episode, decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-tool-tail",
            session_id="sess-tool-tail",
            messages=(
                {"role": "tool", "content": "tool: [1000 lines of pytest output]"},
                {"role": "assistant", "content": "Cleaned up review source tracing and verification passed."},
            ),
            usage=Usage(),
            result="Cleaned up review source tracing and verification passed.",
        )
    )

    assert episode is not None
    assert decision.open_new is True
    assert not episode.title.lower().startswith("episode: tool")
    assert "tool: [1000 lines" not in episode.text
    assert "Cleaned up review source tracing" in episode.text


@pytest.mark.asyncio
async def test_assimilate_run_completed_strips_bundled_tool_prefix_from_assistant_episode_text(db: GraphDatabase):
    from ntrp.agent import Usage
    from ntrp.events.internal import RunCompleted
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    episode, decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-bundled-tool-prefix",
            session_id="sess-bundled-tool-prefix",
            messages=(
                {
                    "role": "assistant",
                    "content": "tool: Todo list updated.\ntool: Remembered knowledge #1.\nassistant: Finished the memory cleanup pass.",
                },
            ),
            usage=Usage(),
            result=None,
        )
    )

    assert episode is not None
    assert decision.open_new is True
    assert not episode.title.lower().startswith("episode: tool")
    assert not episode.text.lower().startswith("assistant: tool:")
    assert "tool: Todo list updated" not in episode.text
    assert "Finished the memory cleanup pass" in episode.text


@pytest.mark.asyncio
async def test_assimilate_run_completed_skips_tool_only_memory_episode(db: GraphDatabase):
    from ntrp.agent import Usage
    from ntrp.events.internal import RunCompleted
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    episode, decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-tool-only",
            session_id="sess-tool-only",
            messages=({"role": "tool", "content": "tool: Todo list updated."},),
            usage=Usage(),
            result=None,
        )
    )

    assert episode is None
    assert decision.open_new is False
    assert decision.boundary_type == "non_narrative_run"
    episodes = await service.list(object_type=KnowledgeObjectType.MEMORY_EPISODE)
    assert episodes == []


@pytest.mark.asyncio
async def test_assimilate_run_completed_explicit_switch_starts_new_episode(db: GraphDatabase):
    from ntrp.agent import Usage
    from ntrp.events.internal import RunCompleted
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    original, _ = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-1",
            session_id="sess-1",
            messages=({"role": "user", "content": "debug memory activation"},),
            usage=Usage(),
            result="Investigating activation.",
        )
    )
    switched, decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-2",
            session_id="sess-1",
            messages=({"role": "user", "content": "new topic: improve automations"},),
            usage=Usage(),
            result="Started automation improvements.",
        )
    )

    assert original is not None
    assert switched is not None
    assert decision.boundary_type == "explicit_switch"
    assert switched.id != original.id
    assert switched.metadata["source_run_ids"] == ["run-2"]
    original_after = await service.get(original.id)
    assert original_after is not None
    assert original_after.metadata["episode_status"] == "closed"


@pytest.mark.asyncio
async def test_run_completion_captures_run_provenance_not_memory_episode(db: GraphDatabase):
    from ntrp.agent import Usage
    from ntrp.events.internal import RunCompleted
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    obj = await service.capture_run_provenance(
        RunCompleted(
            run_id="run-1",
            session_id="sess-1",
            messages=({"role": "assistant", "content": "done"},),
            usage=Usage(prompt_tokens=1, completion_tokens=2),
            result="done",
        )
    )

    assert obj is not None
    assert obj.object_type == KnowledgeObjectType.RUN_PROVENANCE
    assert obj.metadata["memory_role"] == "run_provenance"
    assert obj.status == KnowledgeObjectStatus.ARCHIVED
    assert obj.activation == "audit"
    assert obj.scope == "session:sess-1"
    assert obj.source_ids == ["run:run-1", "session:sess-1"]
    objects = await service.list_many(limit=10)
    assert {item.object_type for item in objects} == {KnowledgeObjectType.RUN_PROVENANCE}

@pytest.mark.asyncio
async def test_model_backed_episode_boundary_classifier_uses_structured_model(monkeypatch):
    from types import SimpleNamespace

    import ntrp.llm.router as router
    from ntrp.knowledge.episodes import ModelBackedEpisodeBoundaryClassifier

    current = KnowledgeObject(
        id=901,
        object_type=KnowledgeObjectType.MEMORY_EPISODE,
        title="Episode: memory work",
        text="Working on memory episodes.",
        status=KnowledgeObjectStatus.ACTIVE,
        scope="session:s1",
        activation="prompt",
        proactiveness_level="L0",
        score=0.0,
        source_ids=[],
        metadata={"episode_status": "open"},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )

    class _Client:
        async def completion(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"continue_current":false,"close_current":true,"open_new":true,'
                                '"boundary_type":"semantic_switch","episode_title":"Episode: automation work",'
                                '"confidence":0.91,"evidence":["topic changed"]}'
                            )
                        )
                    )
                ]
            )

    monkeypatch.setattr(router, "get_completion_client", lambda model: _Client())

    decision = await ModelBackedEpisodeBoundaryClassifier("fake-model").decide(
        current_episode=current,
        event_text="Switching from memory work to automation scheduling.",
    )

    assert decision.close_current is True
    assert decision.open_new is True
    assert decision.boundary_type == "semantic_switch"
    assert decision.episode_title == "Episode: automation work"


@pytest.mark.asyncio
async def test_close_memory_episode_extracts_durable_memory_with_episode_provenance(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    episode = await service.create_memory_episode(
        session_id="sess-extract",
        title="Episode: implement memory retrieval",
        summary="Implemented retrieval cleanup. The user prefers concise source citations.",
        turn_ids=["turn-1"],
        run_ids=["run-1"],
    )

    closed = await service.close_memory_episode(episode.id, outcome="Implemented and tests pass.")

    assert closed is not None
    extracted_ids = closed.metadata.get("extracted_memory_ids")
    assert extracted_ids
    extracted = [await service.get(object_id) for object_id in extracted_ids]
    assert all(obj is not None for obj in extracted)
    assert all(obj.metadata["source_episode_id"] == episode.id for obj in extracted if obj is not None)
    assert all("run-1" in obj.metadata["source_run_ids"] for obj in extracted if obj is not None)
    assert all(f"knowledge:{episode.id}" in obj.source_ids for obj in extracted if obj is not None)

@pytest.mark.asyncio
async def test_episode_close_model_extractor_creates_typed_candidates(db: GraphDatabase, monkeypatch):
    from types import SimpleNamespace

    import ntrp.llm.router as router
    from ntrp.knowledge.entity_extraction import EntityExtractionPipeline
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.model = "fake-model"
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()

    class _Client:
        async def completion(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"memories":[{"object_type":"fact","title":"User wants durable retrieval",'
                                '"text":"The user wants retrieval to prefer durable memories by default.",'
                                '"kind":"preference","confidence":0.88,"source_quote":"prefer durable memories"},'
                                '{"object_type":"pattern","title":"Closed episodes improve extraction",'
                                '"text":"Closing episodes before extraction makes durable memory review easier.",'
                                '"kind":"implementation pattern","confidence":0.9,"source_quote":"episode close"},'
                                '{"object_type":"procedure_candidate","title":"Close episodes before extracting",'
                                '"text":"Extract durable memories only after an episode closes unless the user gives an explicit memory command.",'
                                '"kind":"procedure_candidate","confidence":0.86,"source_quote":"episode close"}]}'
                            )
                        )
                    )
                ]
            )

    monkeypatch.setattr(router, "get_completion_client", lambda model: _Client())
    service = KnowledgeObjectService(memory, entity_pipeline=EntityExtractionPipeline())  # type: ignore[arg-type]
    episode = await service.create_memory_episode(
        session_id="sess-model-extract",
        title="Episode: memory v1",
        summary="The user wants retrieval to prefer durable memories by default and extraction at episode close.",
        run_ids=["run-9"],
    )

    closed = await service.close_memory_episode(episode.id, outcome="Policy implemented.")

    assert closed is not None
    extracted = [await service.get(object_id) for object_id in closed.metadata["extracted_memory_ids"]]
    extracted_types = {obj.object_type for obj in extracted if obj is not None}
    assert KnowledgeObjectType.FACT in extracted_types
    assert KnowledgeObjectType.LESSON in extracted_types
    assert KnowledgeObjectType.PROCEDURE_CANDIDATE not in extracted_types
    assert KnowledgeObjectType.PATTERN not in extracted_types
    normalized = [obj for obj in extracted if obj and obj.metadata.get("normalized_from_object_type") == "procedure_candidate"]
    assert normalized
    assert all(obj.object_type == KnowledgeObjectType.LESSON for obj in normalized)
    assert all(obj.metadata["extractor"] == "episode.close.model.v2" for obj in extracted[:3] if obj is not None)


@pytest.mark.asyncio
async def test_explicit_memory_commands_write_archive_and_supersede(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    remembered = await service.apply_explicit_memory_command(
        "remember the user prefers brutal honesty", source_ids=["run:1"], scope="session:s1"
    )
    always = await service.apply_explicit_memory_command("always cite sources", source_ids=["run:2"], scope="session:s1")
    correction = await service.apply_explicit_memory_command(
        "actually the user prefers brutal honesty with concise wording", source_ids=["run:3"], scope="session:s1"
    )

    assert remembered[0].object_type == KnowledgeObjectType.FACT
    assert always[0].object_type == KnowledgeObjectType.PROCEDURE
    assert correction[0].metadata["kind"] == "correction"

    old = await service.get(remembered[0].id)
    assert old is not None
    assert old.status == KnowledgeObjectStatus.SUPERSEDED
    assert old.superseded_by_object_id == correction[0].id

    archived = await service.apply_explicit_memory_command("forget cite sources", source_ids=["run:4"], scope="session:s1")
    assert archived
    assert archived[0].status == KnowledgeObjectStatus.ARCHIVED


@pytest.mark.asyncio
async def test_activation_uses_durable_memory_by_default_and_evidence_on_source_queries():
    fact = KnowledgeObject(
        id=501,
        object_type=KnowledgeObjectType.FACT,
        title="Memory retrieval policy",
        text="Memory retrieval should prefer durable memories by default.",
        status=KnowledgeObjectStatus.ACTIVE,
        scope=None,
        activation="prompt",
        proactiveness_level="L0",
        score=0.2,
        source_ids=["knowledge:episode-1"],
        metadata={},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    episode = KnowledgeObject(
        id=502,
        object_type=KnowledgeObjectType.MEMORY_EPISODE,
        title="Episode: memory retrieval policy",
        text="Raw episode evidence for memory retrieval policy.",
        status=KnowledgeObjectStatus.ACTIVE,
        scope=None,
        activation="prompt",
        proactiveness_level="L0",
        score=0.9,
        source_ids=["run:1"],
        metadata={"episode_status": "closed"},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )

    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            objects = [fact, episode]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            return objects[offset : offset + limit]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()
    service = KnowledgeActivationService(memory)  # type: ignore[arg-type]

    default = await service.inspect(ActivationRequest(query="memory retrieval policy", budget_chars=2_000))
    evidence = await service.inspect(ActivationRequest(query="source evidence for memory retrieval policy", budget_chars=2_000))

    assert [candidate.object_id for candidate in default.candidates] == ["501"]
    assert "502" in [candidate.object_id for candidate in evidence.candidates]


@pytest.mark.asyncio
async def test_profile_synthesis_creates_source_backed_derived_entity_profile(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]

    fact = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Dex profile fact",
            text="Dex is the user's memory-backed browser copilot project.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:dex-1"],
            metadata={"entities": ["Dex"]},
        )
    )
    await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PATTERN,
            title="Dex profile pattern",
            text="Dex work repeatedly focuses on source-backed memory and inspectable activation.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:dex-2"],
            metadata={"entities": ["Dex"]},
        )
    )

    result = await processors.synthesize_profiles(KnowledgeProfileSynthesisRequest(entity_names=["Dex"], apply=True))

    assert len(result.profiles) == 1
    profile = result.profiles[0]
    assert profile.object_type == KnowledgeObjectType.ENTITY_PROFILE
    assert profile.metadata["memory_tier"] == "profile"
    assert profile.metadata["entities"] == ["Dex"]
    assert profile.metadata["source_anchored"] is True
    assert profile.metadata["valid_as_of"]
    assert profile.metadata["stale_after_days"] == 30
    assert profile.metadata["caveats"]
    assert set(profile.metadata["source_object_ids"]) == {fact.id}
    assert f"knowledge:{fact.id}" in profile.source_ids
    assert "episode:dex-1" in profile.source_ids
    assert "episode:dex-2" not in profile.source_ids
    assert all(section["source_ids"] for section in profile.metadata["profile_sections"])
    assert "Derived profile" in profile.text

    bundle = await KnowledgeActivationService(service).inspect(
        ActivationRequest(query="what do we know about Dex", budget_chars=4_000)
    )
    assert any(
        candidate.object_type == KnowledgeObjectType.ENTITY_PROFILE and candidate.object_id == str(profile.id)
        for candidate in bundle.candidates
    )


@pytest.mark.asyncio
async def test_profile_synthesis_requires_explicit_entity_names_and_does_not_auto_generate_profiles(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]

    for name, title in (
        ("Dex", "real project evidence"),
        ("Regina Lin", "real person evidence"),
        ("Trigger.dev", "real product evidence"),
        ("audit", "generic artifact label"),
        ("automation audit", "borderline topic label"),
        ("quota user-limit cases", "borderline context label"),
        ("AO curriculum", "borderline context label with acronym"),
        ("Stage 1 hard-negative v2", "experiment-stage topic label"),
        ("dex-automations-audit-12-05-25.md", "filename artifact label"),
        ("parseFrontmatter", "code symbol"),
        ("PUBLIC_EXTENSION_ID", "config symbol"),
        ("User", "generic user label"),
    ):
        await service.knowledge_objects.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.FACT,
                title=title,
                text=f"Source-backed detail for {name}.",
                status=KnowledgeObjectStatus.ACTIVE,
                source_ids=[f"episode:{name}"],
                metadata={"entities": [name]},
            )
        )

    result = await processors.synthesize_profiles(KnowledgeProfileSynthesisRequest(limit_entities=10, apply=True))

    assert result.profiles == []
    assert result.skipped == 0
    assert await service.knowledge_objects.get_entity_profile("Dex") is None


@pytest.mark.asyncio
async def test_profile_synthesis_explicit_entity_names_can_be_lowercase_or_topic_like(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]

    await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Explicit lowercase profile target",
            text="automation audit is a user-requested profile target in this test.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:explicit-topic"],
            metadata={"entities": ["automation audit"]},
        )
    )

    result = await processors.synthesize_profiles(
        KnowledgeProfileSynthesisRequest(entity_names=["automation audit"], limit_entities=10, apply=True)
    )

    profile_entities = {profile.metadata["profile_entity"] for profile in result.profiles}
    assert "automation audit" in profile_entities
    profile = result.profiles[0]
    assert profile.metadata["entities"] == ["automation audit"]
    assert profile.source_ids


@pytest.mark.asyncio
async def test_profiles_refresh_progressively_from_scheduled_or_manual_batch(db: GraphDatabase):
    from ntrp.knowledge.profiles import ProfileSynthesisOutput
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    class _ProfileSynthesizer:
        def __init__(self):
            self.calls = []

        async def synthesize(self, *, entity_name, evidence, existing_profile=None):
            self.calls.append((entity_name, [obj.id for obj in evidence], existing_profile.id if existing_profile else None))
            if existing_profile is None:
                text = "# Entity profile: Dex\n\nDerived profile.\n\n## Summary\nDex is the memory-backed browser copilot project."
            else:
                assert "memory-backed browser copilot" in existing_profile.text
                text = (
                    "# Entity profile: Dex\n\n"
                    "Derived profile.\n\n"
                    "## Summary\nDex is the memory-backed browser copilot project after a second source-backed refresh."
                )
            return ProfileSynthesisOutput(
                text=text,
                sections=[{"name": "summary", "summary": "progressive", "source_object_ids": [obj.id for obj in evidence]}],
                synthesis_mode="llm",
            )

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    synthesizer = _ProfileSynthesizer()
    knowledge_objects = KnowledgeObjectService(memory, profile_synthesizer=synthesizer)  # type: ignore[arg-type]
    service = type("_Service", (), {"knowledge_objects": knowledge_objects})()
    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]

    fact = await knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Dex identity",
            text="Dex is the user's memory-backed browser copilot project.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:dex-fact"],
            metadata={"entities": ["Dex"]},
        )
    )

    assert await knowledge_objects.get_entity_profile("Dex") is None
    assert synthesizer.calls == []

    first = await processors.synthesize_profiles(KnowledgeProfileSynthesisRequest(entity_names=["Dex"], limit_entities=10, apply=True))
    assert len(first.profiles) == 1
    created_profile = first.profiles[0]
    assert created_profile.metadata["profile_update_count"] == 1
    assert created_profile.metadata["synthesis_mode"] == "llm"
    assert "[fact]" not in created_profile.text
    assert "Dex identity: Dex identity" not in created_profile.text

    pattern = await knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PATTERN,
            title="Dex activation pattern",
            text="Dex work repeatedly focuses on inspectable activation.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:dex-pattern"],
            metadata={"entities": ["Dex"]},
        )
    )
    unchanged_profile = await knowledge_objects.get_entity_profile("Dex")
    assert unchanged_profile is not None
    assert unchanged_profile.metadata["profile_update_count"] == 1

    second = await processors.synthesize_profiles(KnowledgeProfileSynthesisRequest(entity_names=["Dex"], limit_entities=10, apply=True))
    assert len(second.profiles) == 1
    updated_profile = second.profiles[0]
    assert updated_profile.id == created_profile.id
    assert updated_profile.metadata["profile_update_count"] == 2
    assert updated_profile.metadata["updated_progressively"] is True
    assert set(updated_profile.metadata["source_object_ids"]) == {fact.id}
    assert f"knowledge:{fact.id}" in updated_profile.source_ids
    assert f"knowledge:{pattern.id}" not in updated_profile.source_ids
    assert "inspectable activation" not in updated_profile.text
    assert synthesizer.calls[0][2] is None
    assert synthesizer.calls[1][2] == created_profile.id


@pytest.mark.asyncio
async def test_generated_profile_objects_do_not_trigger_recursive_profile_updates(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    profile = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.ENTITY_PROFILE,
            title="Profile: Dex",
            text="# Entity profile: Dex\n\n## Summary\nDex profile text.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["knowledge:123", "episode:dex"],
            metadata={
                "entities": ["Dex"],
                "profile_entity": "Dex",
                "profile_schema_version": "trimem.profile.v1",
                "source_anchored": True,
                "source_object_ids": [123],
            },
        )
    )

    listed = await service.list_many(object_types={KnowledgeObjectType.ENTITY_PROFILE}, limit=10)
    assert [obj.id for obj in listed] == [profile.id]
    assert profile.metadata["entities"] == ["Dex"]


class _FakeEventWriter:
    async def create(self, **kwargs):
        return None

@pytest.mark.asyncio
async def test_knowledge_objects_vector_search(db: GraphDatabase):
    from tests.conftest import mock_embedding

    repo = KnowledgeObjectRepository(db.conn)
    obj = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Vector-only CUDA memory",
            text="Use bf16 kernels for the GPU allocator path.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )
    await repo.update_embedding(obj.id, mock_embedding("gpu allocator bf16 kernels"))

    results = await repo.search_vector(mock_embedding("gpu allocator bf16 kernels"), limit=5)

    assert results
    assert results[0][0].id == obj.id
    assert results[0][1] > 0.99


@pytest.mark.asyncio
async def test_knowledge_objects_entity_and_temporal_search(db: GraphDatabase):
    from datetime import UTC, datetime

    repo = KnowledgeObjectRepository(db.conn)
    entity_obj = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE,
            title="Prime pod cleanup",
            text="Terminate idle Prime pods after evals finish.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Prime Intellect"]},
        )
    )
    temporal_obj = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Recent memory policy",
            text="Recent memory policy prefers exact source citations.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"happened_at": datetime.now(UTC).isoformat()},
        )
    )

    entity_results = await repo.search_entities("Prime Intellect gpu pods", limit=5)
    temporal_results = await repo.search_temporal("latest memory policy", limit=5)

    assert [obj.id for obj in entity_results] == [entity_obj.id]
    assert temporal_obj.id in [obj.id for obj in temporal_results]


@pytest.mark.asyncio
async def test_activation_includes_vector_only_memory_and_marks_reason():
    vector_obj = KnowledgeObject(
        id=301,
        object_type=KnowledgeObjectType.FACT,
        title="Scheduler draining",
        text="Cordoning the worker prevents queue starvation.",
        status=KnowledgeObjectStatus.ACTIVE,
        scope=None,
        activation="prompt",
        proactiveness_level="L0",
        score=0.1,
        source_ids=["source:vector"],
        metadata={},
        created_at="2026-05-19T00:00:00+00:00",
        updated_at="2026-05-19T00:00:00+00:00",
    )

    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            return []

        async def search_vector(self, query, *, object_types=None, statuses=None, limit: int = 500):
            return [(vector_obj, 0.92)]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()

    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="why are jobs starving", budget_chars=2_000)
    )

    assert [candidate.object_id for candidate in bundle.candidates] == ["301"]
    assert "vector_match" in bundle.candidates[0].reasons


@pytest.mark.asyncio
async def test_activation_omits_metadata_superseded_or_contradicted_memory():
    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            return [
                KnowledgeObject(
                    id=401,
                    object_type=KnowledgeObjectType.FACT,
                    title="Current deploy policy",
                    text="Deploys use the stable release channel.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope=None,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.2,
                    source_ids=["source:current"],
                    metadata={"supersedes_object_id": 402},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
                KnowledgeObject(
                    id=402,
                    object_type=KnowledgeObjectType.FACT,
                    title="Old deploy policy",
                    text="Deploys use the stable release channel.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope=None,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.99,
                    source_ids=["source:old"],
                    metadata={"superseded_by_object_id": 401},
                    created_at="2026-05-18T00:00:00+00:00",
                    updated_at="2026-05-18T00:00:00+00:00",
                ),
            ]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()
    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="deploy stable release channel", budget_chars=2_000)
    )

    assert "401" in [candidate.object_id for candidate in bundle.candidates]
    assert "402" not in [candidate.object_id for candidate in bundle.candidates]

@pytest.mark.asyncio
async def test_activation_records_access_events_not_feedback_objects():
    events = []

    class _AccessEvents:
        async def create(self, **kwargs):
            events.append(kwargs)
            return None

    class _Objects(_FakeKnowledgeObjects):
        async def create(self, payload):  # pragma: no cover - should not be called
            raise AssertionError("activation access should not create knowledge objects")

    memory = _FakeMemoryService()
    memory.access_events = _AccessEvents()
    memory.knowledge_objects = _Objects()

    await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="dex automation alerts", task="chat_context", record_access=True, budget_chars=2_000)
    )

    assert events
    assert events[0]["source"] == "chat_context"
    assert events[0]["policy_version"] == "knowledge.activation.v2"
    assert events[0]["details"]["candidates"][0]["score"]
    assert events[0]["details"]["candidates"][0]["selected"] is True
    assert events[0]["details"]["candidates"][0]["rank"] == 1
    assert events[0]["details"]["candidates"][0]["reasons"]
    assert events[0]["details"]["candidates"][0]["signals"]
    assert events[0]["details"]["candidates"][0]["source_ids"]
    assert events[0]["details"]["candidates"][0]["chars"] > 0
    assert events[0]["details"]["omitted_count"] >= 0
    if events[0]["details"]["omitted"]:
        assert events[0]["details"]["omitted"][0]["selected"] is False
        assert events[0]["details"]["omitted"][0]["rank"] == len(events[0]["details"]["candidates"]) + 1
    assert events[0]["omitted_fact_ids"] is not None


@pytest.mark.asyncio
async def test_memory_activation_query_penalizes_mechinterp_activation_ambiguity():
    class _Objects(_FakeKnowledgeObjects):
        async def list_many(self, *, object_types=None, statuses=None, limit: int = 100, offset: int = 0):
            objects = [
                KnowledgeObject(
                    id=31,
                    object_type=KnowledgeObjectType.PATTERN,
                    title="Activation oracles for MATS mechinterp",
                    text="Activation oracle work for mechanistic interpretability probes and LatentQA.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope=None,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.7,
                    source_ids=["legacy-observation:31"],
                    metadata={},
                    created_at="2026-05-18T00:00:00+00:00",
                    updated_at="2026-05-18T00:00:00+00:00",
                ),
                KnowledgeObject(
                    id=32,
                    object_type=KnowledgeObjectType.FACT,
                    title="Memory activation trace table",
                    text="Memory activation access is stored in telemetry and should expose retrieved and injected knowledge traces.",
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope=None,
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.35,
                    source_ids=["knowledge:trace"],
                    metadata={"kind": "memory_activation"},
                    created_at="2026-05-18T00:00:00+00:00",
                    updated_at="2026-05-18T00:00:00+00:00",
                ),
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[offset : offset + limit]

    memory = _FakeMemoryService()
    memory.knowledge_objects = _Objects()
    bundle = await KnowledgeActivationService(memory).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="what do we have in activations", budget_chars=2_000)
    )

    assert bundle.candidates[0].object_id == "32"
    ambiguous = next(candidate for candidate in bundle.candidates + bundle.omitted if candidate.object_id == "31")
    assert "ambiguous_activation_domain" in ambiguous.reasons


@pytest.mark.asyncio
async def test_first_run_completion_closes_episode_and_extracts(db: GraphDatabase):
    from ntrp.agent import Usage
    from ntrp.events.internal import RunCompleted
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    episode, decision = await service.assimilate_run_completed(
        RunCompleted(
            run_id="run-single-done",
            session_id="sess-single-done",
            messages=({"role": "assistant", "content": "implemented and tests pass"},),
            usage=Usage(),
            result="Implemented and tests pass.",
        )
    )

    assert episode is not None
    assert decision.close_current is True
    assert episode.metadata["episode_status"] == "closed"
    assert episode.metadata.get("extracted_memory_ids")


@pytest.mark.asyncio
async def test_explicit_forget_is_scope_safe(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    scoped = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Scoped deploy policy",
            text="Deploy policy uses canary release.",
            status=KnowledgeObjectStatus.ACTIVE,
            scope="session:a",
        )
    )
    other = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Other staging cleanup",
            text="Staging cleanup runs weekly.",
            status=KnowledgeObjectStatus.ACTIVE,
            scope="session:b",
        )
    )

    archived = await service.apply_explicit_memory_command("forget deploy policy", scope="session:a")

    assert [obj.id for obj in archived] == [scoped.id]
    assert (await service.get(scoped.id)).status == KnowledgeObjectStatus.ARCHIVED  # type: ignore[union-attr]
    assert (await service.get(other.id)).status == KnowledgeObjectStatus.ACTIVE  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_memory_search_source_indexes_only_active_durable_objects(db: GraphDatabase):
    repo = KnowledgeObjectRepository(db.conn)
    active = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Active durable memory",
            text="Active durable memory should be indexed.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )
    archived = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Archived durable memory",
            text="Archived durable memory should not be indexed.",
            status=KnowledgeObjectStatus.ARCHIVED,
        )
    )
    draft = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
            title="Draft procedure candidate",
            text="Draft candidate should not be indexed.",
            status=KnowledgeObjectStatus.DRAFT,
        )
    )

    items = await MemorySearchSource(db).scan()
    ids = {item.source_id for item in items}

    assert f"knowledge:{active.id}" in ids
    assert f"knowledge:{archived.id}" not in ids
    assert f"knowledge:{draft.id}" not in ids


@pytest.mark.asyncio
async def test_benchmark_memory_suite_runs_against_seeded_long_term_memory(db: GraphDatabase):
    from ntrp.knowledge.evals import benchmark_memory_suite, run_memory_eval_suite
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    current_policy = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Current Dex deploy channel policy",
            text="Current Dex deploy channel policy: Dex currently deploys through the canary channel after smoke checks.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:dex-current"],
            metadata={"entities": ["Dex"]},
        )
    )
    stale_policy = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Stale Dex deploy channel policy",
            text="Stale Dex deploy channel policy: Dex previously deployed directly to stable without smoke checks.",
            status=KnowledgeObjectStatus.SUPERSEDED,
            source_ids=["episode:dex-stale"],
            metadata={"entities": ["Dex"]},
        )
    )
    dex_profile = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.ENTITY_PROFILE,
            title="Profile: Dex",
            text="# Entity profile: Dex\n\n## Summary\nDex is the memory-backed browser copilot project.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=[f"knowledge:{current_policy.id}"],
            metadata={
                "entities": ["Dex"],
                "profile_entity": "Dex",
                "profile_schema_version": "trimem.profile.v1",
                "source_anchored": True,
                "source_object_ids": [current_policy.id],
            },
        )
    )
    prime_procedure = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE,
            title="Prime pod cleanup procedure",
            text="For Prime pod cleanup, terminate idle pods after evals finish and verify disk snapshots first.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:prime-procedure"],
            metadata={"entities": ["Prime"]},
        )
    )

    current_preference = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Current editor preference",
            text="User currently prefers Neovim for focused coding sessions.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:editor-current"],
            metadata={"entities": ["User", "Neovim"]},
        )
    )
    stale_preference = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Stale editor preference",
            text="User previously preferred VS Code as the default editor.",
            status=KnowledgeObjectStatus.SUPERSEDED,
            source_ids=["episode:editor-stale"],
            metadata={"entities": ["User", "VS Code"]},
        )
    )
    assistant_recommendation = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Assistant recommended Trigger deploy check",
            text="Assistant recommended checking recent Trigger.dev task runs before changing release automation.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:trigger-recommendation"],
            metadata={"entities": ["Trigger.dev", "Dex"]},
        )
    )
    dex_slack_decision = await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Dex Slack sync retry decision",
            text="We decided Dex Slack sync should retry Slack 429 responses with jitter before surfacing an alert.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:dex-slack-decision"],
            metadata={"entities": ["Dex", "Slack"]},
        )
    )

    dex_episode = await service.knowledge_objects.create_memory_episode(
        session_id="bench-session",
        title="Dex profile continuity evidence",
        summary="Source episode showing Dex profile continuity and deploy policy updates.",
        source_ids=["session:bench-session"],
        episode_status="closed",
    )

    suite = benchmark_memory_suite(
        {
            "current_policy": str(current_policy.id),
            "stale_policy": str(stale_policy.id),
            "dex_profile": str(dex_profile.id),
            "prime_procedure": str(prime_procedure.id),
            "dex_episode": str(dex_episode.id),
            "current_preference": str(current_preference.id),
            "stale_preference": str(stale_preference.id),
            "assistant_recommendation": str(assistant_recommendation.id),
            "dex_slack_decision": str(dex_slack_decision.id),
        }
    )
    result = await run_memory_eval_suite(KnowledgeActivationService(service), suite, budget_chars=6_000, limit=10)

    assert result.passed
    assert result.case_count == 8
    assert result.recall == 1.0


@pytest.mark.asyncio
async def test_memory_eval_harness_flags_stale_or_poisoned_retrieval():
    from ntrp.knowledge.evals import MemoryEvalCase, run_memory_eval_cases

    service = KnowledgeActivationService(_FakeMemoryService())  # type: ignore[arg-type]
    result = await run_memory_eval_cases(
        service,
        [
            MemoryEvalCase(
                name="dex-current-alerting",
                query="dex automation alerts",
                expected_object_ids={"1"},
                forbidden_object_ids={"5"},
            )
        ],
    )

    assert result.passed
    assert result.cases[0].retrieved_object_ids[0] == "1"


def test_entity_cleaning_rejects_source_ids_and_numeric_metrics():
    from ntrp.knowledge.entity_extraction import (
        EntityExtractionProposal,
        EntityMentionProposal,
        resolve_entity_proposal,
    )

    result = resolve_entity_proposal(
        EntityExtractionProposal(
            entities=[
                EntityMentionProposal(surface="session:20260510_235813_387", canonical_name="session:20260510_235813_387", confidence=0.95),
                EntityMentionProposal(surface="1628", canonical_name="1628", confidence=0.95),
                EntityMentionProposal(surface="8 runs", canonical_name="8 runs", confidence=0.95),
                EntityMentionProposal(surface="Trigger.dev", canonical_name="Trigger.dev", confidence=0.95),
            ]
        ),
        source_ids=["knowledge:18028"],
        extractor_name="test",
    )

    assert result.names == ["Trigger.dev"]


@pytest.mark.asyncio
async def test_reflect_ignores_legacy_run_episode_rows(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = type("_Service", (), {})()
    service.knowledge_objects = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    processors = KnowledgeProcessorService(service)  # type: ignore[arg-type]

    await service.knowledge_objects.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.EPISODE,
            title="Run noisy",
            text="Session: 20260510_235813_387\nRun: noisy\nResult: done",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["run:noisy"],
        )
    )

    reflected = await processors.reflect(KnowledgeReflectRequest(limit=10))

    assert reflected.created == []
    assert reflected.skipped == 0


@pytest.mark.asyncio
async def test_long_episode_snippets_keep_multiple_sources_within_budget():
    class _Objects:
        async def search_text(self, query, *, object_types=None, statuses=None, limit: int = 100):
            filler = " generic filler text" * 700
            objects = [
                KnowledgeObject(
                    id=31,
                    object_type=KnowledgeObjectType.MEMORY_EPISODE,
                    title="Tomato seed session",
                    text=(
                        "LongMemEval session answer_tomatoes\n"
                        "Date: 2023/03/01\n"
                        "user: I started the tomatoes in seed trays on March 1."
                        f"{filler}"
                    ),
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="personal",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.0,
                    source_ids=["answer_tomatoes"],
                    metadata={"episode_status": "closed"},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
                KnowledgeObject(
                    id=32,
                    object_type=KnowledgeObjectType.MEMORY_EPISODE,
                    title="Marigold seed session",
                    text=(
                        "LongMemEval session answer_marigolds\n"
                        "Date: 2023/03/03\n"
                        "user: I started the marigolds in seed trays on March 3."
                        f"{filler}"
                    ),
                    status=KnowledgeObjectStatus.ACTIVE,
                    scope="personal",
                    activation="prompt",
                    proactiveness_level="L0",
                    score=0.0,
                    source_ids=["answer_marigolds"],
                    metadata={"episode_status": "closed"},
                    created_at="2026-05-19T00:00:00+00:00",
                    updated_at="2026-05-19T00:00:00+00:00",
                ),
            ]
            if object_types:
                objects = [obj for obj in objects if obj.object_type in object_types]
            if statuses:
                objects = [obj for obj in objects if obj.status in statuses]
            return objects[:limit]

        async def search_entities(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

        async def search_temporal(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

    class _Memory(_FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.knowledge_objects = _Objects()

    service = KnowledgeActivationService(_Memory())  # type: ignore[arg-type]

    bundle = await service.inspect(
        ActivationRequest(
            query="Which seeds were started first, the tomatoes or the marigolds?",
            scope="personal",
            budget_chars=5_000,
            limit=10,
        )
    )

    assert {source_id for candidate in bundle.candidates for source_id in candidate.source_ids} == {
        "answer_tomatoes",
        "answer_marigolds",
    }
    assert all("focused_evidence_snippet" in candidate.reasons for candidate in bundle.candidates)
    assert all(len(candidate.text) < 2_500 for candidate in bundle.candidates)


@pytest.mark.asyncio
async def test_long_episode_snippets_keep_adjacent_answer_context():
    class _Objects:
        async def search_text(self, query, *, object_types=None, statuses=None, limit: int = 100):
            filler = " unrelated grocery planning filler" * 500
            obj = KnowledgeObject(
                id=33,
                object_type=KnowledgeObjectType.MEMORY_EPISODE,
                title="Coupon redemption session",
                text=(
                    "LongMemEval session answer_coupon\n"
                    "Date: 2023/03/07\n"
                    "user: I redeemed a $5 coupon on coffee creamer last Sunday.\n"
                    "user: I used that coffee creamer coupon at Target before buying snacks.\n"
                    f"{filler}"
                ),
                status=KnowledgeObjectStatus.ACTIVE,
                scope="personal",
                activation="prompt",
                proactiveness_level="L0",
                score=0.0,
                source_ids=["answer_coupon"],
                metadata={"episode_status": "closed"},
                created_at="2026-05-19T00:00:00+00:00",
                updated_at="2026-05-19T00:00:00+00:00",
            )
            objects = [obj]
            if object_types:
                objects = [item for item in objects if item.object_type in object_types]
            if statuses:
                objects = [item for item in objects if item.status in statuses]
            return objects[:limit]

        async def search_entities(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

        async def search_temporal(self, query, *, object_types=None, statuses=None, limit: int = 100):
            return []

    class _Memory(_FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.knowledge_objects = _Objects()

    bundle = await KnowledgeActivationService(_Memory()).inspect(  # type: ignore[arg-type]
        ActivationRequest(
            query="Where did I redeem a $5 coupon on coffee creamer?",
            scope="personal",
            budget_chars=2_500,
            limit=5,
        )
    )

    assert len(bundle.candidates) == 1
    assert "redeemed a $5 coupon on coffee creamer" in bundle.candidates[0].text
    assert "Target" in bundle.candidates[0].text
    assert len(bundle.candidates[0].text) < 2_500


@pytest.mark.asyncio
async def test_memory_create_policy_archives_unsourced_profiles_and_large_patterns(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    profile = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.ENTITY_PROFILE,
            title="Profile: Garbage",
            text="A profile without provenance should not be active.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=[],
            metadata={"profile_entity": "Garbage"},
        )
    )
    assert profile.status == KnowledgeObjectStatus.ARCHIVED
    assert profile.metadata["create_policy_reason"] == "entity_profiles_must_be_source_backed"

    large_pattern = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PATTERN,
            title="Huge rollup",
            text="noisy summary\n" * 80,
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["episode:noisy"],
            metadata={},
        )
    )
    assert large_pattern.status == KnowledgeObjectStatus.ARCHIVED
    assert large_pattern.metadata["create_policy_reason"] == "large_pattern_summaries_are_not_active_memory"

    legacy_procedure = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
            title="Legacy workflow candidate",
            text="A stale episode extractor should not recreate procedure_candidate drafts.",
            status=KnowledgeObjectStatus.DRAFT,
            scope="session:test",
            activation="review",
            source_ids=["knowledge:episode-1"],
            metadata={"extractor": "episode.close.model.v1", "kind": "workflow"},
        )
    )
    assert legacy_procedure.object_type == KnowledgeObjectType.LESSON
    assert legacy_procedure.status == KnowledgeObjectStatus.ACTIVE
    assert legacy_procedure.activation == "prompt"
    assert legacy_procedure.metadata["normalized_from_object_type"] == "procedure_candidate"
    assert (
        legacy_procedure.metadata["create_policy_reason"]
        == "episode_extractor_legacy_procedure_normalized_to_lesson"
    )


@pytest.mark.asyncio
async def test_memory_episode_create_archives_oldest_rows_over_session_cap(db: GraphDatabase):
    from ntrp.memory.service import KnowledgeObjectService

    class _Memory:
        pass

    memory = _Memory()
    memory.db = db
    memory.facts = type("_Facts", (), {"read_conn": db.conn})()
    memory.events = _FakeEventWriter()
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    created = []
    for idx in range(32):
        created.append(
            await service.create_memory_episode(
                session_id="cap-test",
                title=f"Episode {idx}",
                summary=f"Useful short episode {idx}",
            )
        )

    refreshed = [await service.get(item.id) for item in created]
    active = [item for item in refreshed if item is not None and item.status == KnowledgeObjectStatus.ACTIVE]
    archived = [item for item in refreshed if item is not None and item.status == KnowledgeObjectStatus.ARCHIVED]
    assert len(active) == 30
    assert {item.id for item in archived} == {created[0].id, created[1].id}
    assert all(item.metadata["archived_reason"] == "memory_episode_retention_cap" for item in archived)
