from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ntrp.logging import get_logger
from ntrp.memory.audit import (
    DEFAULT_PRUNE_LIMIT,
    DEFAULT_PRUNE_MAX_SOURCES,
    DEFAULT_PRUNE_OLDER_THAN_DAYS,
    memory_audit,
    observation_prune_candidates_by_ids,
    observation_prune_candidates_matching,
    observation_prune_dry_run,
)
from ntrp.memory.fact_review import FactMetadataSuggestion, suggest_fact_metadata
from ntrp.memory.facts import PROFILE_FACT_KINDS, FactMemory, SessionMemory
from ntrp.memory.injection_policy import DEFAULT_INJECTION_CHAR_BUDGET, memory_injection_policy_preview
from ntrp.memory.learning_policy import (
    LEARNING_POLICY_SOURCE_TYPE,
    LEARNING_POLICY_VERSION,
    build_memory_policy_proposals,
)
from ntrp.memory.models import (
    Dream,
    EntityRef,
    Fact,
    FactContext,
    FactKind,
    LearningCandidate,
    LearningEvent,
    MemoryAccessEvent,
    MemoryEvent,
    Observation,
    SourceType,
)
from ntrp.memory.profile_policy import (
    DEFAULT_PROFILE_CHAR_BUDGET,
    DEFAULT_PROFILE_FACT_CHAR_BUDGET,
    DEFAULT_PROFILE_REVIEW_ACCESS_COUNT,
    ProfilePolicyPreview,
    profile_policy_preview,
)

_logger = get_logger(__name__)


@dataclass(frozen=True)
class LearningProposalScanResult:
    proposals_considered: int
    created_events: list[LearningEvent]
    created_candidates: list[LearningCandidate]
    skipped_candidates: list[LearningCandidate]


class FactService:
    def __init__(
        self,
        memory: FactMemory,
        enqueue_fact_index_upsert: Callable[[int, str], Awaitable[bool]] | None = None,
        enqueue_fact_index_delete: Callable[[int], Awaitable[bool]] | None = None,
    ):
        self._memory = memory
        self._enqueue_fact_index_upsert = enqueue_fact_index_upsert
        self._enqueue_fact_index_delete = enqueue_fact_index_delete

    async def list_recent(self, limit: int = 100, offset: int = 0) -> tuple[list[Fact], int]:
        total = await self._memory.facts.count_active()
        facts = await self._memory.facts.list_recent(limit=limit, offset=offset)
        return facts, total

    async def list_filtered(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        kind: FactKind | None = None,
        source_type: SourceType | None = None,
        status: str = "active",
        accessed: str | None = None,
        entity: str | None = None,
    ) -> tuple[list[Fact], int]:
        return await self._memory.facts.list_filtered(
            limit=limit,
            offset=offset,
            kind=kind,
            source_type=source_type,
            status=status,
            accessed=accessed,
            entity=entity,
        )

    async def list_kind_review(self, limit: int = 100, offset: int = 0) -> tuple[list[Fact], int]:
        return await self._memory.facts.list_kind_review(limit=limit, offset=offset)

    async def suggest_kind_review(
        self,
        *,
        fact_ids: list[int] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[Fact, FactMetadataSuggestion]], int]:
        if fact_ids:
            now = datetime.now(UTC)
            facts_by_id = await self._memory.facts.get_batch(fact_ids)
            facts = [
                fact
                for fact_id in fact_ids
                if (fact := facts_by_id.get(fact_id)) is not None
                and fact.kind == FactKind.NOTE
                and fact.archived_at is None
                and fact.superseded_by_fact_id is None
                and (fact.expires_at is None or fact.expires_at > now)
            ]
            total = len(facts)
        else:
            facts, total = await self._memory.facts.list_kind_review(limit=limit, offset=offset)

        suggestions = await suggest_fact_metadata(facts, self._memory.model)
        facts_by_id = {fact.id: fact for fact in facts}
        return [(facts_by_id[suggestion.fact_id], suggestion) for suggestion in suggestions], total

    async def list_supersession_candidates(self, limit: int = 100) -> list[dict]:
        rows = await self._memory.facts.list_supersession_candidates(PROFILE_FACT_KINDS, limit=limit)
        fact_ids = sorted({row["older_fact_id"] for row in rows} | {row["newer_fact_id"] for row in rows})
        facts = await self._memory.facts.get_batch(fact_ids)

        candidates = []
        for row in rows:
            older = facts.get(row["older_fact_id"])
            newer = facts.get(row["newer_fact_id"])
            if not older or not newer:
                continue
            candidates.append(
                {
                    "kind": row["kind"],
                    "entity": row["entity_name"],
                    "older_fact": older,
                    "newer_fact": newer,
                    "reason": "same entity and fact kind; review whether newer fact supersedes older fact",
                }
            )
        return candidates

    async def get(self, fact_id: int) -> tuple[Fact, list[EntityRef]]:
        if not (fact := await self._memory.facts.get(fact_id)):
            raise KeyError(f"Fact {fact_id} not found")
        entity_refs = await self._memory.facts.get_entity_refs(fact_id)
        return fact, entity_refs

    async def update(self, fact_id: int, new_text: str) -> tuple[Fact, list[dict]]:
        async with self._memory.transaction():
            repo = self._memory.facts

            old = await repo.get(fact_id)
            if not old:
                raise KeyError(f"Fact {fact_id} not found")

            new_embedding = await self._memory.embedder.embed_one(new_text)
            await repo.delete_entity_refs(fact_id)
            await repo.update_text(fact_id, new_text, new_embedding)

            extraction = await self._memory.extractor.extract(new_text)
            await self._memory._process_extraction(fact_id, extraction)

            fact = await repo.get(fact_id)
            if not fact:
                raise RuntimeError(f"Fact {fact_id} disappeared during update")
            await self._memory.events.create(
                actor="user",
                action="fact.updated",
                target_type="fact",
                target_id=fact_id,
                source_type=old.source_type.value,
                source_ref=old.source_ref,
                reason="manual fact text edit",
                policy_version="memory.api.v1",
                details={"old_chars": len(old.text), "new_chars": len(new_text)},
            )

        if self._enqueue_fact_index_upsert:
            await self._enqueue_fact_index_upsert(fact_id, new_text)

        entity_refs = await repo.get_entity_refs(fact_id)
        return fact, [{"name": e.name, "entity_id": e.entity_id} for e in entity_refs]

    async def update_metadata(self, fact_id: int, updates: dict[str, object]) -> Fact:
        async with self._memory.transaction():
            repo = self._memory.facts
            old = await repo.get(fact_id)
            if not old:
                raise KeyError(f"Fact {fact_id} not found")

            superseded_by = updates.get("superseded_by_fact_id")
            if superseded_by is not None:
                if superseded_by == fact_id:
                    raise ValueError("fact cannot supersede itself")
                if not (await repo.get(int(superseded_by))):
                    raise ValueError("superseding fact not found")

            fact = await repo.update_metadata(fact_id, updates)
            if not fact:
                raise RuntimeError(f"Fact {fact_id} disappeared during metadata update")
            if updates:
                await self._memory.events.create(
                    actor="user",
                    action="fact.metadata_updated",
                    target_type="fact",
                    target_id=fact_id,
                    source_type=old.source_type.value,
                    source_ref=old.source_ref,
                    reason="manual fact metadata edit",
                    policy_version="memory.api.v1",
                    details={"updates": updates, "fields": sorted(updates)},
                )

        return fact

    async def count_unconsolidated(self) -> int:
        return await self._memory.facts.count_unconsolidated()

    async def delete(self, fact_id: int) -> dict:
        async with self._memory.transaction():
            repo = self._memory.facts

            fact = await repo.get(fact_id)
            if not fact:
                raise KeyError(f"Fact {fact_id} not found")

            entity_refs_count = await repo.count_entity_refs(fact_id)
            await repo.delete(fact_id)
            await self._memory.observations.remove_source_facts([fact_id])
            await self._memory.dreams.remove_source_facts([fact_id])
            await repo.cleanup_orphaned_entities()
            await self._memory.events.create(
                actor="user",
                action="fact.deleted",
                target_type="fact",
                target_id=fact_id,
                source_type=fact.source_type.value,
                source_ref=fact.source_ref,
                reason="manual fact delete",
                policy_version="memory.api.v1",
                details={"entity_refs": entity_refs_count, "kind": fact.kind.value},
            )

        if self._enqueue_fact_index_delete:
            await self._enqueue_fact_index_delete(fact_id)
        return {"entity_refs": entity_refs_count}


class ObservationService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def list_recent(self, limit: int = 50) -> list[Observation]:
        return await self._memory.observations.list_recent(limit=limit)

    async def list_filtered(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str = "active",
        accessed: str | None = None,
        min_sources: int | None = None,
        max_sources: int | None = None,
    ) -> tuple[list[Observation], int]:
        return await self._memory.observations.list_filtered(
            limit=limit,
            offset=offset,
            status=status,
            accessed=accessed,
            min_sources=min_sources,
            max_sources=max_sources,
        )

    async def get(self, observation_id: int) -> tuple[Observation, list[Fact], list[int], list[int]]:
        if not (obs := await self._memory.observations.get(observation_id)):
            raise KeyError(f"Observation {observation_id} not found")
        fact_ids = await self._memory.observations.get_fact_ids(observation_id)
        facts_by_id = await self._memory.facts.get_batch(fact_ids)
        missing_fact_ids = [fact_id for fact_id in fact_ids if fact_id not in facts_by_id]
        return obs, [facts_by_id[fact_id] for fact_id in fact_ids if fact_id in facts_by_id], fact_ids, missing_fact_ids

    async def update(self, observation_id: int, new_summary: str) -> Observation:
        async with self._memory.transaction():
            obs_repo = self._memory.observations

            old = await obs_repo.get(observation_id)
            if not old:
                raise KeyError(f"Observation {observation_id} not found")

            new_embedding = await self._memory.embedder.embed_one(new_summary)
            obs = await obs_repo.update_summary(observation_id, new_summary, new_embedding)
            if not obs:
                raise RuntimeError(f"Observation {observation_id} disappeared during update")
            await self._memory.events.create(
                actor="user",
                action="observation.updated",
                target_type="observation",
                target_id=observation_id,
                reason="manual pattern summary edit",
                policy_version="memory.api.v1",
                details={
                    "old_chars": len(old.summary),
                    "new_chars": len(new_summary),
                    "support_count": len(old.source_fact_ids),
                },
            )

        return obs

    async def delete(self, observation_id: int) -> None:
        async with self._memory.transaction():
            obs_repo = self._memory.observations

            obs = await obs_repo.get(observation_id)
            if not obs:
                raise KeyError(f"Observation {observation_id} not found")

            await obs_repo.delete(observation_id)
            await self._memory.events.create(
                actor="user",
                action="observation.deleted",
                target_type="observation",
                target_id=observation_id,
                reason="manual pattern delete",
                policy_version="memory.api.v1",
                details={"support_count": len(obs.source_fact_ids)},
            )


class DreamService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def list_recent(self, limit: int = 50) -> list[Dream]:
        return await self._memory.dreams.list_recent(limit=limit)

    async def get(self, dream_id: int) -> tuple[Dream, list[Fact]]:
        if not (dream := await self._memory.dreams.get(dream_id)):
            raise KeyError(f"Dream {dream_id} not found")
        facts_by_id = await self._memory.facts.get_batch(dream.source_fact_ids)
        return dream, list(facts_by_id.values())

    async def delete(self, dream_id: int) -> None:
        dream = await self._memory.dreams.get(dream_id)
        if not dream:
            raise KeyError(f"Dream {dream_id} not found")
        async with self._memory.transaction():
            await self._memory.dreams.delete(dream_id)
            await self._memory.events.create(
                actor="user",
                action="dream.deleted",
                target_type="dream",
                target_id=dream_id,
                reason="manual dream delete",
                policy_version="memory.api.v1",
                details={"support_count": len(dream.source_fact_ids)},
            )


class MemoryEventService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        target_type: str | None = None,
        target_id: int | None = None,
        action: str | None = None,
    ) -> list[MemoryEvent]:
        return await self._memory.events.list_recent(
            limit=limit,
            offset=offset,
            target_type=target_type,
            target_id=target_id,
            action=action,
        )


class MemoryAccessEventService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        source: str | None = None,
    ) -> list[MemoryAccessEvent]:
        return await self._memory.access_events.list_recent(
            limit=limit,
            offset=offset,
            source=source,
        )

    async def policy_preview(
        self,
        *,
        limit: int = 100,
        char_budget: int = 3000,
    ) -> dict:
        events = await self._memory.access_events.list_recent(limit=limit)
        return memory_injection_policy_preview(events, char_budget=char_budget)


class LearningService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def create_event(
        self,
        *,
        source_type: str,
        scope: str,
        signal: str,
        source_id: str | None = None,
        evidence_ids: list[str] | None = None,
        outcome: str = "unknown",
        details: dict | None = None,
    ) -> LearningEvent:
        async with self._memory.transaction():
            return await self._memory.learning.create_event(
                source_type=source_type,
                source_id=source_id,
                scope=scope,
                signal=signal,
                evidence_ids=evidence_ids,
                outcome=outcome,
                details=details,
            )

    async def list_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        scope: str | None = None,
        source_type: str | None = None,
    ) -> list[LearningEvent]:
        return await self._memory.learning.list_events(
            limit=limit,
            offset=offset,
            scope=scope,
            source_type=source_type,
        )

    async def create_candidate(
        self,
        *,
        change_type: str,
        target_key: str,
        proposal: str,
        rationale: str,
        evidence_event_ids: list[int] | None = None,
        expected_metric: str | None = None,
        policy_version: str,
        status: str = "proposed",
        details: dict | None = None,
    ) -> LearningCandidate:
        async with self._memory.transaction():
            return await self._memory.learning.create_candidate(
                change_type=change_type,
                target_key=target_key,
                proposal=proposal,
                rationale=rationale,
                evidence_event_ids=evidence_event_ids,
                expected_metric=expected_metric,
                policy_version=policy_version,
                status=status,
                details=details,
            )

    async def list_candidates(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        change_type: str | None = None,
    ) -> list[LearningCandidate]:
        return await self._memory.learning.list_candidates(
            limit=limit,
            offset=offset,
            status=status,
            change_type=change_type,
        )

    async def update_candidate_status(self, candidate_id: int, status: str) -> LearningCandidate:
        async with self._memory.transaction():
            candidate = await self._memory.learning.update_candidate_status(candidate_id, status)
            if not candidate:
                raise KeyError(f"Learning candidate {candidate_id} not found")
            return candidate

    async def propose_from_memory_policy(
        self,
        *,
        access_limit: int = 100,
        injection_char_budget: int = DEFAULT_INJECTION_CHAR_BUDGET,
        profile_limit: int = 100,
        prune_older_than_days: int = DEFAULT_PRUNE_OLDER_THAN_DAYS,
        prune_max_sources: int = DEFAULT_PRUNE_MAX_SOURCES,
        prune_limit: int = DEFAULT_PRUNE_LIMIT,
    ) -> LearningProposalScanResult:
        injection_events = await self._memory.access_events.list_recent(limit=access_limit)
        injection_preview = memory_injection_policy_preview(
            injection_events,
            char_budget=injection_char_budget,
        )
        profile_facts = await self._memory.get_profile(limit=20)
        review_facts = await self._memory.facts.list_profile_review_candidates(
            PROFILE_FACT_KINDS,
            min_salience=2,
            min_access_count=DEFAULT_PROFILE_REVIEW_ACCESS_COUNT,
            limit=profile_limit,
        )
        profile_preview = profile_policy_preview(
            profile_facts=profile_facts,
            review_facts=review_facts,
            char_budget=DEFAULT_PROFILE_CHAR_BUDGET,
            fact_char_budget=DEFAULT_PROFILE_FACT_CHAR_BUDGET,
            review_access_count=DEFAULT_PROFILE_REVIEW_ACCESS_COUNT,
        )
        prune_preview = await observation_prune_dry_run(
            self._memory.observations.read_conn,
            older_than_days=prune_older_than_days,
            max_sources=prune_max_sources,
            limit=prune_limit,
        )
        proposals = build_memory_policy_proposals(
            injection_preview=injection_preview,
            profile_preview=profile_preview,
            prune_preview=prune_preview,
        )

        created_events: list[LearningEvent] = []
        created_candidates: list[LearningCandidate] = []
        skipped_candidates: list[LearningCandidate] = []

        async with self._memory.transaction():
            for proposal in proposals:
                existing = await self._memory.learning.find_open_candidate(
                    change_type=proposal.change_type,
                    target_key=proposal.target_key,
                )
                if existing:
                    skipped_candidates.append(existing)
                    continue

                event = await self._memory.learning.create_event(
                    source_type=LEARNING_POLICY_SOURCE_TYPE,
                    source_id=proposal.source_id,
                    scope=proposal.scope,
                    signal=proposal.signal,
                    evidence_ids=list(proposal.evidence_ids),
                    outcome="proposed",
                    details=proposal.details,
                )
                candidate = await self._memory.learning.create_candidate(
                    change_type=proposal.change_type,
                    target_key=proposal.target_key,
                    proposal=proposal.proposal,
                    rationale=proposal.rationale,
                    evidence_event_ids=[event.id],
                    expected_metric=proposal.expected_metric,
                    policy_version=LEARNING_POLICY_VERSION,
                    details={"source_event_id": event.id, **proposal.details},
                )
                created_events.append(event)
                created_candidates.append(candidate)

        return LearningProposalScanResult(
            proposals_considered=len(proposals),
            created_events=created_events,
            created_candidates=created_candidates,
            skipped_candidates=skipped_candidates,
        )


class MemoryService:
    def __init__(
        self,
        memory: FactMemory,
        enqueue_fact_index_upsert: Callable[[int, str], Awaitable[bool]] | None = None,
        enqueue_fact_index_delete: Callable[[int], Awaitable[bool]] | None = None,
        enqueue_memory_index_clear: Callable[[], Awaitable[bool]] | None = None,
    ):
        self.memory = memory
        self._enqueue_memory_index_clear = enqueue_memory_index_clear
        self.facts = FactService(memory, enqueue_fact_index_upsert, enqueue_fact_index_delete)
        self.observations = ObservationService(memory)
        self.dreams = DreamService(memory)
        self.events = MemoryEventService(memory)
        self.access_events = MemoryAccessEventService(memory)
        self.learning = LearningService(memory)

    @property
    def is_consolidating(self) -> bool:
        return self.memory.is_consolidating

    async def stats(self) -> dict[str, int]:
        return {
            "fact_count": await self.memory.facts.count(),
            "observation_count": await self.memory.observations.count(),
            "dream_count": await self.memory.dreams.count(),
            "archived_fact_count": await self.memory.facts.count_archived(),
            "archived_observation_count": await self.memory.observations.count_archived(),
        }

    async def audit(self) -> dict:
        return await memory_audit(self.memory.facts.read_conn)

    async def profile(self, limit: int = 6) -> list[Fact]:
        return await self.memory.get_profile(limit=limit)

    async def profile_policy_preview(
        self,
        *,
        limit: int = 100,
        profile_limit: int = 20,
        char_budget: int = DEFAULT_PROFILE_CHAR_BUDGET,
        fact_char_budget: int = DEFAULT_PROFILE_FACT_CHAR_BUDGET,
        review_access_count: int = DEFAULT_PROFILE_REVIEW_ACCESS_COUNT,
    ) -> ProfilePolicyPreview:
        profile_facts = await self.memory.get_profile(limit=profile_limit)
        review_facts = await self.memory.facts.list_profile_review_candidates(
            PROFILE_FACT_KINDS,
            min_salience=2,
            min_access_count=review_access_count,
            limit=limit,
        )
        return profile_policy_preview(
            profile_facts=profile_facts,
            review_facts=review_facts,
            char_budget=char_budget,
            fact_char_budget=fact_char_budget,
            review_access_count=review_access_count,
        )

    async def inspect_recall(self, *, query: str, limit: int = 5) -> tuple[FactContext, SessionMemory]:
        context = await self.memory.inspect_recall(query=query, limit=limit)
        session_memory = await self.memory.get_session_memory()
        return context, session_memory

    async def repair_missing_embeddings(self, *, limit: int = 100, apply: bool = False) -> dict:
        return await self.memory.repair_missing_embeddings(limit=limit, apply=apply)

    async def prune_observations_dry_run(
        self,
        *,
        older_than_days: int = 30,
        max_sources: int = 5,
        limit: int = 100,
    ) -> dict:
        return await observation_prune_dry_run(
            self.memory.observations.read_conn,
            older_than_days=older_than_days,
            max_sources=max_sources,
            limit=limit,
        )

    async def prune_observations_apply(
        self,
        *,
        observation_ids: list[int],
        all_matching: bool = False,
        older_than_days: int = 30,
        max_sources: int = 5,
    ) -> dict:
        requested_ids = list(dict.fromkeys(observation_ids))
        async with self.memory.transaction():
            if all_matching:
                candidates = await observation_prune_candidates_matching(
                    self.memory.observations.conn,
                    older_than_days=older_than_days,
                    max_sources=max_sources,
                )
            else:
                candidates = await observation_prune_candidates_by_ids(
                    self.memory.observations.conn,
                    requested_ids,
                    older_than_days=older_than_days,
                    max_sources=max_sources,
                )
            archive_ids = [row["id"] for row in candidates]
            archived = await self.memory.observations.archive_batch(archive_ids)
            archive_id_set = set(archive_ids)
            skipped_ids = [] if all_matching else [obs_id for obs_id in requested_ids if obs_id not in archive_id_set]
            if archived:
                await self.memory.events.create(
                    actor="user",
                    action="observations.archived",
                    target_type="observation_batch",
                    reason="manual prune apply",
                    policy_version="memory.prune.v1",
                    details={
                        "ids": archive_ids,
                        "requested_ids": requested_ids,
                        "skipped_ids": skipped_ids,
                        "all_matching": all_matching,
                        "criteria": {
                            "older_than_days": older_than_days,
                            "max_sources": max_sources,
                        },
                    },
                )

        return {
            "status": "archived" if archived else "unchanged",
            "archived": archived,
            "archived_ids": archive_ids,
            "skipped_ids": skipped_ids,
            "candidates": candidates,
        }

    async def count_unconsolidated(self) -> int:
        return await self.memory.facts.count_unconsolidated()

    async def clear(self) -> dict[str, int]:
        deleted = await self.memory.clear()
        if self._enqueue_memory_index_clear:
            await self._enqueue_memory_index_clear()
        return deleted

    async def clear_observations(self) -> dict[str, int]:
        return await self.memory.clear_observations()
