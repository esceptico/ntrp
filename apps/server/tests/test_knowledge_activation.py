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
    KnowledgePruneRequest,
    KnowledgePublishRequest,
    KnowledgeReflectRequest,
)
from ntrp.knowledge.processors import KnowledgeProcessorService
from ntrp.knowledge.store import KnowledgeObjectRepository
from ntrp.memory.search_source import MemorySearchSource
from ntrp.memory.store.base import GraphDatabase


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
            KnowledgeObjectType.EPISODE.value: 2,
            KnowledgeObjectType.FACT.value: 1,
            KnowledgeObjectType.PATTERN.value: 1,
            KnowledgeObjectType.LESSON.value: 1,
            KnowledgeObjectType.PROCEDURE.value: 1,
            KnowledgeObjectType.PROCEDURE_CANDIDATE.value: 1,
            KnowledgeObjectType.ACTION_CANDIDATE.value: 1,
            KnowledgeObjectType.ARTIFACT.value: 1,
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
        "Episodes",
        "Facts",
        "Patterns",
        "Lessons",
        "Procedures",
        "Improve",
        "Actions",
        "Artifacts",
        "Activation",
    ]
    counts = {surface.object_type: surface.count for surface in summary.surfaces}
    assert counts[KnowledgeObjectType.EPISODE] == 2
    assert counts[KnowledgeObjectType.FACT] == 1
    assert counts[KnowledgeObjectType.PROCEDURE] == 1
    assert counts[KnowledgeObjectType.OUTCOME_FEEDBACK] == 1
    assert {surface.name: surface.count for surface in summary.surfaces}["Lessons"] == 1
    assert {surface.name: surface.count for surface in summary.surfaces}["Actions"] == 1
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
    assert KnowledgeObjectType.PATTERN in types
    assert KnowledgeObjectType.PROCEDURE_CANDIDATE in types
    assert KnowledgeObjectType.ACTION_CANDIDATE in types

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

    updated = await service.knowledge_objects.update(
        next(obj.id for obj in reflected.created if obj.object_type == KnowledgeObjectType.PROCEDURE_CANDIDATE),
        KnowledgeObjectUpdate(status=KnowledgeObjectStatus.APPROVED),
    )
    assert updated.status == KnowledgeObjectStatus.APPROVED
    procedures = await service.knowledge_objects.list(object_type=KnowledgeObjectType.PROCEDURE)
    assert len(procedures) == 1

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
    assert old is not None
    assert old.status == KnowledgeObjectStatus.SUPERSEDED
    assert len([item for item in procedures if item.status == KnowledgeObjectStatus.ACTIVE]) == 1


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
    assert obj.activation == "audit"
    assert obj.scope == "session:sess-1"

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
    assert KnowledgeObjectType.FACT in {obj.object_type for obj in extracted if obj is not None}
    assert KnowledgeObjectType.PROCEDURE_CANDIDATE in {obj.object_type for obj in extracted if obj is not None}
    assert all(obj.metadata["extractor"] == "episode.close.model.v1" for obj in extracted[:2] if obj is not None)


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
