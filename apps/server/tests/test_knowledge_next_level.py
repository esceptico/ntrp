import json

import pytest

from ntrp.knowledge import (
    ActivationRequest,
    KnowledgeActivationService,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeSupersessionProposal,
)
from ntrp.knowledge.entity_extraction import (
    EntityExtractionPipeline,
    EntityExtractionProposal,
    EntityMentionProposal,
    EntityRelationProposal,
    EntityResolutionResult,
    ResolvedEntity,
)
from ntrp.knowledge.evals import MemoryEvalCase, MemoryEvalSuite, run_memory_eval_suite
from ntrp.knowledge.store import KnowledgeObjectRepository
from ntrp.memory.service import KnowledgeObjectService
from ntrp.memory.store.base import GraphDatabase
from tests.conftest import mock_embedding


class _FakeEventWriter:
    async def create(self, **kwargs):
        return None


class _MockEmbedder:
    async def embed(self, texts):
        return [mock_embedding(text) for text in texts]

    async def embed_one(self, text):
        return mock_embedding(text)


class _ProposalExtractor:
    name = "test.model.entity_extractor"

    def __init__(self, proposal: EntityExtractionProposal):
        self.proposal = proposal

    async def extract(self, title: str, text: str, *, source_ids: list[str]) -> EntityExtractionProposal:
        return self.proposal


class _Memory:
    def __init__(self, db: GraphDatabase):
        self.db = db
        self.facts = type("_Facts", (), {"read_conn": db.conn})()
        self.events = _FakeEventWriter()
        self.embedder = _MockEmbedder()

    def transaction(self):
        return self.db_transaction()

    async def db_transaction(self):  # pragma: no cover - not called directly
        raise AssertionError("use async context manager")


class _TransactionMemory(_Memory):
    class _Tx:
        def __init__(self, db: GraphDatabase):
            self.db = db

        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            if exc_type:
                await self.db.conn.rollback()
            else:
                await self.db.conn.commit()
            return False

    def transaction(self):
        return self._Tx(self.db)


@pytest.mark.asyncio
async def test_knowledge_service_backfills_old_object_embeddings(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    repo = KnowledgeObjectRepository(db.conn)
    obj = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Old unembedded knowledge",
            text="Old knowledge should receive a vector during production backfill.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )

    dry = await service.backfill_embeddings(limit=10, apply=False)
    applied = await service.backfill_embeddings(limit=10, batch_size=2, apply=True)
    results = await repo.search_vector(mock_embedding("Old unembedded knowledge vector"), limit=5)

    assert dry["total_missing"] >= 1
    assert obj.id in dry["object_ids"]
    assert applied["repaired"] >= 1
    assert obj.id in [result[0].id for result in results]


@pytest.mark.asyncio
async def test_knowledge_service_promotes_procedure_candidate_to_lesson(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    repo = KnowledgeObjectRepository(db.conn)

    candidate = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE_CANDIDATE,
            title="Candidate: inspect prod run first",
            text="When debugging production, inspect the real run before static reasoning.",
            status=KnowledgeObjectStatus.DRAFT,
            scope="dex",
            source_ids=["episode:prod-run"],
        )
    )

    updated = await service.update(candidate.id, KnowledgeObjectUpdate(status=KnowledgeObjectStatus.APPROVED))
    promoted = await repo.list(object_type=KnowledgeObjectType.LESSON, status=KnowledgeObjectStatus.ACTIVE)

    assert updated.status == KnowledgeObjectStatus.APPROVED
    assert len(promoted) == 1
    assert promoted[0].object_type == KnowledgeObjectType.LESSON
    assert promoted[0].text == candidate.text
    assert promoted[0].metadata["approved_candidate_id"] == candidate.id
    assert promoted[0].metadata["promoted_from"] == KnowledgeObjectType.PROCEDURE_CANDIDATE.value


@pytest.mark.asyncio
async def test_knowledge_service_extracts_entity_graph_metadata(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.PROCEDURE,
            title="Prime Intellect pod cleanup",
            text="Prime Intellect uses Trigger.dev to terminate idle GPU pods.",
            status=KnowledgeObjectStatus.ACTIVE,
            source_ids=["project:prime-intellect"],
        )
    )

    assert "Prime Intellect" in obj.metadata["entities"]
    assert "Prime Intellect" in await service._repo.get_entity_names(obj.id)
    assert "Trigger.dev" in await service._repo.get_entity_names(obj.id)
    assert obj.metadata["entity_graph"]["edges"]
    assert any(edge["relation"] == "uses" for edge in obj.metadata["entity_graph"]["edges"])


@pytest.mark.asyncio
async def test_entity_pipeline_dedupes_aliases_and_skips_ambiguous_entities(db: GraphDatabase):
    memory = _TransactionMemory(db)
    pipeline = EntityExtractionPipeline(
        primary=_ProposalExtractor(
            EntityExtractionProposal(
                entities=[
                    EntityMentionProposal(
                        surface="Trigger.dev",
                        canonical_name="Trigger.dev",
                        entity_type="service",
                        aliases=["Trigger", "trigger dot dev"],
                        confidence=0.94,
                    ),
                    EntityMentionProposal(
                        surface="Trigger",
                        canonical_name="Trigger.dev",
                        entity_type="service",
                        aliases=["trigger.dev"],
                        confidence=0.82,
                    ),
                    EntityMentionProposal(
                        surface="Atlas",
                        canonical_name="Atlas",
                        confidence=0.7,
                        resolution="ambiguous",
                        ambiguity_candidates=["MongoDB Atlas", "Atlas project"],
                    ),
                ],
                relations=[
                    EntityRelationProposal(source="Trigger", relation="runs", target="Trigger.dev", confidence=0.9)
                ],
            )
        )
    )
    service = KnowledgeObjectService(memory, entity_pipeline=pipeline)  # type: ignore[arg-type]

    obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Trigger alias test",
            text="Trigger.dev is also called Trigger in chat.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )

    assert obj.metadata["entities"] == ["Trigger.dev"]
    assert obj.metadata["entity_graph"]["aliases"] == {"Trigger.dev": ["Trigger", "trigger dot dev"]}
    assert obj.metadata["entity_graph"]["unresolved"][0]["surface"] == "Atlas"
    assert await service._repo.get_entity_names(obj.id) == ["Trigger.dev"]


@pytest.mark.asyncio
async def test_entity_update_replaces_extractor_owned_refs_and_keeps_manual_entities(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Dex uses Trigger.dev",
            text="Dex uses Trigger.dev for durable workflows.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Manual Entity"]},
        )
    )
    assert "Trigger.dev" in await service._repo.get_entity_names(obj.id)

    updated = await service.update(
        obj.id,
        KnowledgeObjectUpdate(
            title="Prime Intellect uses Runpod",
            text="Prime Intellect uses Runpod for GPU experiments.",
        ),
    )
    names = await service._repo.get_entity_names(obj.id)

    assert "Manual Entity" in updated.metadata["entities"]
    assert "Trigger.dev" not in updated.metadata["entities"]
    assert "Trigger.dev" not in names
    assert "Prime Intellect" in names
    assert "Runpod" in names


@pytest.mark.asyncio
async def test_entity_search_matches_alias_metadata(db: GraphDatabase):
    memory = _TransactionMemory(db)
    pipeline = EntityExtractionPipeline(
        primary=_ProposalExtractor(
            EntityExtractionProposal(
                entities=[
                    EntityMentionProposal(
                        surface="Trigger.dev",
                        canonical_name="Trigger.dev",
                        entity_type="service",
                        aliases=["Trigger"],
                        confidence=0.95,
                    )
                ]
            )
        )
    )
    service = KnowledgeObjectService(memory, entity_pipeline=pipeline)  # type: ignore[arg-type]
    obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Trigger.dev preference",
            text="Trigger.dev is preferred for durable task orchestration.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )

    results = await service._repo.search_entities("Trigger", statuses={KnowledgeObjectStatus.ACTIVE})

    assert [result.id for result in results] == [obj.id]


@pytest.mark.asyncio
async def test_entity_resolution_layer_persists_mentions_aliases_and_candidates(db: GraphDatabase):
    memory = _TransactionMemory(db)
    pipeline = EntityExtractionPipeline(
        primary=_ProposalExtractor(
            EntityExtractionProposal(
                entities=[
                    EntityMentionProposal(
                        surface="Trigger.dev",
                        canonical_name="Trigger.dev",
                        entity_type="service",
                        aliases=["Trigger"],
                        confidence=0.95,
                        evidence_quote="Trigger.dev runs durable jobs",
                    )
                ]
            )
        )
    )
    service = KnowledgeObjectService(memory, entity_pipeline=pipeline)  # type: ignore[arg-type]

    obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Trigger.dev jobs",
            text="Trigger.dev runs durable jobs.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )

    mentions = await db.conn.execute_fetchall(
        "SELECT * FROM entity_mentions WHERE knowledge_object_id = ?",
        (obj.id,),
    )
    aliases = await db.conn.execute_fetchall(
        """
        SELECT ea.alias_text, ea.alias_type
        FROM entity_aliases ea
        JOIN entities e ON e.id = ea.entity_id
        WHERE e.name = 'Trigger.dev'
        ORDER BY ea.alias_type, ea.alias_text
        """,
    )
    candidates = await db.conn.execute_fetchall(
        "SELECT method, decision_status, score FROM entity_resolution_candidates WHERE mention_id = ?",
        (mentions[0]["id"],),
    )

    assert mentions[0]["surface_text"] == "Trigger.dev"
    assert mentions[0]["resolution_status"] == "resolved"
    assert {tuple(row) for row in aliases} >= {("Trigger.dev", "canonical"), ("Trigger", "extracted")}
    assert candidates[0]["method"] == "new_entity"
    assert candidates[0]["decision_status"] == "accepted"
    assert candidates[0]["score"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_entity_resolution_keeps_alias_collisions_ambiguous_with_candidates(db: GraphDatabase):
    memory = _TransactionMemory(db)
    repo = KnowledgeObjectRepository(db.conn)
    first = await repo._get_or_create_entity(ResolvedEntity(name="Trigger.dev", entity_type="service"))
    second = await repo._get_or_create_entity(ResolvedEntity(name="Trigger CRM", entity_type="service"))
    await repo._insert_alias(first, "Trigger", alias_type="nickname", confidence=0.9)
    await repo._insert_alias(second, "Trigger", alias_type="nickname", confidence=0.9)
    await db.conn.commit()

    pipeline = EntityExtractionPipeline(
        primary=_ProposalExtractor(
            EntityExtractionProposal(
                entities=[
                    EntityMentionProposal(
                        surface="Trigger",
                        canonical_name="Trigger",
                        entity_type="service",
                        confidence=0.8,
                    )
                ]
            )
        )
    )
    service = KnowledgeObjectService(memory, entity_pipeline=pipeline)  # type: ignore[arg-type]
    obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Trigger ambiguity",
            text="Trigger is important here.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )

    mentions = await db.conn.execute_fetchall(
        "SELECT * FROM entity_mentions WHERE knowledge_object_id = ?",
        (obj.id,),
    )
    candidates = await db.conn.execute_fetchall(
        "SELECT candidate_entity_id, decision_status FROM entity_resolution_candidates WHERE mention_id = ? ORDER BY rank",
        (mentions[0]["id"],),
    )
    refs = await repo.get_entity_names(obj.id)
    edges = await db.conn.execute_fetchall(
        "SELECT relation, status FROM entity_identity_edges WHERE relation = 'possible_same_as'",
    )

    assert mentions[0]["resolution_status"] == "ambiguous"
    assert {row["candidate_entity_id"] for row in candidates} == {first, second}
    assert all(row["decision_status"] == "needs_review" for row in candidates)
    assert refs == []
    assert edges[0]["status"] == "needs_review"


@pytest.mark.asyncio
async def test_entity_resolution_dedupes_alias_candidates_before_identity_edges(db: GraphDatabase):
    repo = KnowledgeObjectRepository(db.conn)
    entity_id = await repo._get_or_create_entity(ResolvedEntity(name="Trigger MCP", entity_type="service"))
    await repo._insert_alias(entity_id, "Trigger", alias_type="nickname", confidence=0.9)
    await repo._insert_alias(entity_id, "Trigger MCP", alias_type="nickname", confidence=0.9)
    obj = await repo.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Trigger MCP audit",
            text="Trigger MCP exposes production run state.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )

    await repo.replace_entity_resolution(
        obj.id,
        EntityResolutionResult(
            entities=(
                ResolvedEntity(
                    name="Trigger",
                    entity_type="service",
                    aliases=("Trigger MCP",),
                    confidence=0.8,
                    mentions=("Trigger MCP",),
                ),
            ),
            extractor="test",
        ),
    )

    mentions = await db.conn.execute_fetchall(
        "SELECT * FROM entity_mentions WHERE knowledge_object_id = ?",
        (obj.id,),
    )
    candidates = await db.conn.execute_fetchall(
        "SELECT candidate_entity_id, method, decision_status FROM entity_resolution_candidates WHERE mention_id = ?",
        (mentions[0]["id"],),
    )
    edges = await db.conn.execute_fetchall("SELECT * FROM entity_identity_edges")

    assert mentions[0]["resolution_status"] == "resolved"
    assert [tuple(row) for row in candidates] == [(entity_id, "exact_alias", "accepted")]
    assert edges == []


@pytest.mark.asyncio
async def test_entity_merge_and_split_are_reversible_resolution_commits(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    first_obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Trigger.dev workflow",
            text="Trigger.dev runs workflows.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )
    second_obj = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Trigger workflow",
            text="Trigger runs workflows.",
            status=KnowledgeObjectStatus.ACTIVE,
        )
    )
    first_entity = await db.conn.execute_fetchall(
        """
        SELECT entity_id FROM knowledge_entity_refs
        WHERE knowledge_object_id = ? AND name = 'Trigger.dev'
        """,
        (first_obj.id,),
    )
    second_entity = await db.conn.execute_fetchall(
        """
        SELECT entity_id FROM knowledge_entity_refs
        WHERE knowledge_object_id = ? AND name = 'Trigger'
        """,
        (second_obj.id,),
    )
    winner_id = int(first_entity[0]["entity_id"])
    loser_id = int(second_entity[0]["entity_id"])

    merge_commit_id = await service._repo.commit_entity_merge(
        winner_id,
        loser_id,
        reason="manual review confirmed alias",
        confidence=0.99,
    )
    loser = await db.conn.execute_fetchall("SELECT lifecycle_status, merged_into_entity_id FROM entities WHERE id = ?", (loser_id,))
    merge_commit = await db.conn.execute_fetchall("SELECT * FROM entity_resolution_commits WHERE id = ?", (merge_commit_id,))
    same_as = await db.conn.execute_fetchall("SELECT relation, commit_id FROM entity_identity_edges WHERE relation = 'same_as'")

    assert dict(loser[0]) == {"lifecycle_status": "merged", "merged_into_entity_id": winner_id}
    assert merge_commit[0]["action"] == "merge"
    assert json.loads(merge_commit[0]["reversible_patch"])["loser"]
    assert same_as[0]["commit_id"] == merge_commit_id

    mention = await db.conn.execute_fetchall(
        "SELECT id FROM entity_mentions WHERE knowledge_object_id = ? LIMIT 1",
        (second_obj.id,),
    )
    split_commit_id = await service._repo.commit_entity_split(
        winner_id,
        new_entity_name="Trigger CRM",
        mention_ids=[int(mention[0]["id"])],
        reason="later evidence says this was a different Trigger",
        confidence=0.9,
    )
    split_commit = await db.conn.execute_fetchall("SELECT * FROM entity_resolution_commits WHERE id = ?", (split_commit_id,))
    not_same = await db.conn.execute_fetchall("SELECT relation, commit_id FROM entity_identity_edges WHERE relation = 'not_same_as'")

    assert split_commit[0]["action"] == "split"
    assert json.loads(split_commit[0]["reversible_patch"])["moved_mentions"]
    assert not_same[0]["commit_id"] == split_commit_id


@pytest.mark.asyncio
async def test_knowledge_service_supersedes_semantic_conflicts_and_activation_suppresses_old(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]
    memory_service = type("_MemoryService", (), {"knowledge_objects": service, "events": type("_Events", (), {"list_recent": lambda self, limit=20: []})()})()

    old = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Deploy release channel",
            text="Dex deploys should use the stable release channel.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Dex"]},
        )
    )
    new = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Deploy release channel",
            text="Dex deploys should use the canary release channel.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Dex"]},
        )
    )
    old_after = await service.get(old.id)

    bundle = await KnowledgeActivationService(memory_service).inspect(  # type: ignore[arg-type]
        ActivationRequest(query="Dex deploy release channel", budget_chars=2_000, include_actions=False)
    )

    assert old_after is not None
    assert old_after.status == KnowledgeObjectStatus.SUPERSEDED
    assert old_after.superseded_by_object_id == new.id
    assert old_after.superseded_at is not None
    assert old_after.supersession_reason == "conflicting_value_pair"
    assert old_after.metadata["superseded_by_object_id"] == new.id
    assert old.id in new.metadata["contradicts_object_ids"]
    assert str(new.id) in [candidate.object_id for candidate in bundle.candidates]
    assert str(old.id) not in [candidate.object_id for candidate in bundle.candidates]


@pytest.mark.asyncio
async def test_model_proposed_supersession_requires_deterministic_overlap(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    old = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Dex release policy",
            text="Dex releases should use stable for deploys.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Dex"]},
        )
    )
    new = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Dex release policy",
            text="Dex releases now use canary for deploys.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Dex"]},
        )
    )

    # The new object may already supersede the old one via the local detector; make
    # a separate pair to test the explicit model-proposal commit path.
    if (await service.get(old.id)).status == KnowledgeObjectStatus.SUPERSEDED:  # type: ignore[union-attr]
        old = await service.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.FACT,
                title="Dex rollout window",
                text="Dex rollout window is mornings.",
                status=KnowledgeObjectStatus.ACTIVE,
                metadata={"entities": ["Dex"]},
            )
        )
        new = await service.create(
            KnowledgeObjectCreate(
                object_type=KnowledgeObjectType.FACT,
                title="Dex rollout window",
                text="Dex rollout window is afternoons.",
                status=KnowledgeObjectStatus.ACTIVE,
                metadata={"entities": ["Dex"]},
            )
        )

    result = await service.commit_supersession_proposal(
        KnowledgeSupersessionProposal(
            superseded_object_id=old.id,
            superseding_object_id=new.id,
            reason="model proposed newer Dex policy",
            confidence=0.81,
            proposed_by="test.model",
            evidence_terms=["Dex", "policy"],
        )
    )

    old_after = await service.get(old.id)
    assert result.committed
    assert old_after is not None
    assert old_after.status == KnowledgeObjectStatus.SUPERSEDED
    assert old_after.superseded_by_object_id == new.id
    assert old_after.supersession_reason == "model proposed newer Dex policy"


@pytest.mark.asyncio
async def test_model_proposed_supersession_rejects_unrelated_objects(db: GraphDatabase):
    memory = _TransactionMemory(db)
    service = KnowledgeObjectService(memory)  # type: ignore[arg-type]

    old = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Dex release policy",
            text="Dex releases use stable.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Dex"]},
        )
    )
    unrelated = await service.create(
        KnowledgeObjectCreate(
            object_type=KnowledgeObjectType.FACT,
            title="Prime GPU policy",
            text="Prime pods use H100 GPUs.",
            status=KnowledgeObjectStatus.ACTIVE,
            metadata={"entities": ["Prime Intellect"]},
        )
    )

    result = await service.commit_supersession_proposal(
        KnowledgeSupersessionProposal(
            superseded_object_id=old.id,
            superseding_object_id=unrelated.id,
            reason="bad model proposal",
            confidence=0.95,
            proposed_by="test.model",
        )
    )

    old_after = await service.get(old.id)
    assert not result.committed
    assert result.reason == "insufficient_overlap"
    assert old_after is not None
    assert old_after.status == KnowledgeObjectStatus.ACTIVE


@pytest.mark.asyncio
async def test_memory_eval_suite_reports_precision_recall():
    class _Inspector:
        async def inspect(self, request: ActivationRequest):
            from ntrp.knowledge.models import ActivationBundle, ActivationCandidate

            candidates = [
                ActivationCandidate(
                    object_type=KnowledgeObjectType.FACT,
                    object_id="good",
                    title="Good",
                    text="Good memory",
                    score=1.0,
                )
            ]
            return ActivationBundle(
                query=request.query,
                scope=request.scope,
                budget_chars=request.budget_chars,
                used_chars=11,
                candidates=candidates,
                omitted=[],
            )

    result = await run_memory_eval_suite(
        _Inspector(),
        MemoryEvalSuite(
            name="tiny",
            cases=[MemoryEvalCase(name="case", query="good", expected_object_ids={"good"}, forbidden_object_ids={"bad"})],
        ),
    )

    assert result.passed
    assert result.case_count == 1
    assert result.pass_count == 1
    assert result.precision == 1.0
    assert result.recall == 1.0
