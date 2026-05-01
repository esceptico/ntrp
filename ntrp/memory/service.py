from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from ntrp.logging import get_logger
from ntrp.memory.audit import memory_audit, observation_prune_candidates_by_ids, observation_prune_dry_run
from ntrp.memory.fact_review import FactMetadataSuggestion, suggest_fact_metadata
from ntrp.memory.facts import PROFILE_FACT_KINDS, FactMemory
from ntrp.memory.models import Dream, EntityRef, Fact, FactKind, MemoryEvent, Observation, SourceType

_logger = get_logger(__name__)


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

    async def get(self, observation_id: int) -> tuple[Observation, list[Fact]]:
        if not (obs := await self._memory.observations.get(observation_id)):
            raise KeyError(f"Observation {observation_id} not found")
        fact_ids = await self._memory.observations.get_fact_ids(observation_id)
        facts_by_id = await self._memory.facts.get_batch(fact_ids)
        return obs, [facts_by_id[fact_id] for fact_id in fact_ids if fact_id in facts_by_id]

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
        older_than_days: int = 30,
        max_sources: int = 5,
    ) -> dict:
        requested_ids = list(dict.fromkeys(observation_ids))
        async with self.memory.transaction():
            candidates = await observation_prune_candidates_by_ids(
                self.memory.observations.conn,
                requested_ids,
                older_than_days=older_than_days,
                max_sources=max_sources,
            )
            archive_ids = [row["id"] for row in candidates]
            archived = await self.memory.observations.archive_batch(archive_ids)
            archive_id_set = set(archive_ids)
            skipped_ids = [obs_id for obs_id in requested_ids if obs_id not in archive_id_set]
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
