from ntrp.channel import Channel
from ntrp.constants import EXTRACTION_CONTEXT_MESSAGES, EXTRACTION_EVERY_N_TURNS
from ntrp.events.internal import FactDeleted, FactUpdated, MemoryCleared, RunCompleted
from ntrp.logging import get_logger
from ntrp.memory.chat_extraction import extract_from_chat
from ntrp.memory.facts import FactMemory
from ntrp.memory.models import Dream, EntityRef, Fact, Observation

_logger = get_logger(__name__)


class FactService:
    def __init__(self, memory: FactMemory, channel: Channel):
        self._memory = memory
        self._channel = channel

    async def list_recent(self, limit: int = 100, offset: int = 0) -> tuple[list[Fact], int]:
        total = await self._memory.facts.count()
        facts = await self._memory.facts.list_recent(limit=limit, offset=offset)
        return facts, total

    async def get(self, fact_id: int) -> tuple[Fact, list[EntityRef]]:
        fact = await self._memory.facts.get(fact_id)
        if not fact:
            raise KeyError(f"Fact {fact_id} not found")
        entity_refs = await self._memory.facts.get_entity_refs(fact_id)
        return fact, entity_refs

    async def update(self, fact_id: int, new_text: str) -> tuple[Fact, list[dict]]:
        async with self._memory.transaction():
            repo = self._memory.facts

            fact = await repo.get(fact_id)
            if not fact:
                raise KeyError(f"Fact {fact_id} not found")

            new_embedding = await self._memory.embedder.embed_one(new_text)
            await repo.delete_entity_refs(fact_id)
            await repo.update_text(fact_id, new_text, new_embedding)

            extraction = await self._memory.extractor.extract(new_text)
            await self._memory._process_extraction(fact_id, extraction)

            fact = await repo.get(fact_id)

        self._channel.publish(FactUpdated(fact_id=fact_id, text=new_text))

        entity_refs = await repo.get_entity_refs(fact_id)
        return fact, [{"name": e.name, "entity_id": e.entity_id} for e in entity_refs]

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
            await repo.cleanup_orphaned_entities()

        self._channel.publish(FactDeleted(fact_id=fact_id))
        return {"entity_refs": entity_refs_count}


class ObservationService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def list_recent(self, limit: int = 50) -> list[Observation]:
        return await self._memory.observations.list_recent(limit=limit)

    async def get(self, observation_id: int) -> tuple[Observation, list[Fact]]:
        obs = await self._memory.observations.get(observation_id)
        if not obs:
            raise KeyError(f"Observation {observation_id} not found")
        fact_ids = await self._memory.observations.get_fact_ids(observation_id)
        facts_by_id = await self._memory.facts.get_batch(fact_ids)
        return obs, list(facts_by_id.values())

    async def update(self, observation_id: int, new_summary: str) -> Observation:
        async with self._memory.transaction():
            obs_repo = self._memory.observations

            obs = await obs_repo.get(observation_id)
            if not obs:
                raise KeyError(f"Observation {observation_id} not found")

            new_embedding = await self._memory.embedder.embed_one(new_summary)
            obs = await obs_repo.update_summary(observation_id, new_summary, new_embedding)

        return obs

    async def delete(self, observation_id: int) -> None:
        async with self._memory.transaction():
            obs_repo = self._memory.observations

            obs = await obs_repo.get(observation_id)
            if not obs:
                raise KeyError(f"Observation {observation_id} not found")

            await obs_repo.delete(observation_id)


class DreamService:
    def __init__(self, memory: FactMemory):
        self._memory = memory

    async def list_recent(self, limit: int = 50) -> list[Dream]:
        return await self._memory.dreams.list_recent(limit=limit)

    async def get(self, dream_id: int) -> tuple[Dream, list[Fact]]:
        dream = await self._memory.dreams.get(dream_id)
        if not dream:
            raise KeyError(f"Dream {dream_id} not found")
        facts_by_id = await self._memory.facts.get_batch(dream.source_fact_ids)
        return dream, list(facts_by_id.values())

    async def delete(self, dream_id: int) -> None:
        dream = await self._memory.dreams.get(dream_id)
        if not dream:
            raise KeyError(f"Dream {dream_id} not found")
        async with self._memory.transaction():
            await self._memory.dreams.delete(dream_id)


class MemoryService:
    def __init__(self, memory: FactMemory, channel: Channel):
        self.memory = memory
        self.channel = channel
        self.facts = FactService(memory, channel)
        self.observations = ObservationService(memory)
        self.dreams = DreamService(memory)
        self._cursors: dict[str, int] = {}
        self._turn_counts: dict[str, int] = {}
        channel.subscribe(RunCompleted, self._on_run_completed)

    async def _on_run_completed(self, event: RunCompleted) -> None:
        if event.result is None or not event.messages:
            return

        sid = event.session_id
        self._turn_counts[sid] = self._turn_counts.get(sid, 0) + 1
        if self._turn_counts[sid] % EXTRACTION_EVERY_N_TURNS != 0:
            return

        cursor = self._cursors.get(sid, 0)
        context_start = max(0, cursor - EXTRACTION_CONTEXT_MESSAGES)
        window = event.messages[context_start:]
        if not window:
            return

        facts = await extract_from_chat(tuple(window), self.memory.extraction_model)
        new_cursor = len(event.messages)
        self._cursors[sid] = new_cursor

        if not facts:
            return
        _logger.info("Extracted %d facts from chat", len(facts))
        source_ref = f"{sid}:{context_start}-{new_cursor}"
        for fact_text in facts:
            await self.memory.remember(
                text=fact_text,
                source_type="chat",
                source_ref=source_ref,
            )

    def close(self) -> None:
        self.channel.unsubscribe(RunCompleted, self._on_run_completed)

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

    async def count_unconsolidated(self) -> int:
        return await self.memory.facts.count_unconsolidated()

    async def clear(self) -> dict[str, int]:
        deleted = await self.memory.clear()
        self.channel.publish(MemoryCleared())
        return deleted

    async def clear_observations(self) -> dict[str, int]:
        return await self.memory.clear_observations()
