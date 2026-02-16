from ntrp.channel import Channel
from ntrp.events import FactDeleted, FactUpdated
from ntrp.memory.facts import FactMemory
from ntrp.memory.models import Fact, Observation


class MemoryService:
    """Admin/dashboard operations on the memory system.

    FactMemory owns agent-facing ops (remember, recall, forget).
    MemoryService owns admin ops (update_fact, delete_observation, etc).
    """

    def __init__(self, memory: FactMemory, channel: Channel):
        self.memory = memory
        self.channel = channel

    async def update_fact(self, fact_id: int, new_text: str) -> tuple[Fact, list[dict]]:
        async with self.memory.transaction():
            repo = self.memory.facts

            fact = await repo.get(fact_id)
            if not fact:
                raise KeyError(f"Fact {fact_id} not found")

            new_embedding = await self.memory.embedder.embed_one(new_text)
            await repo.delete_entity_refs(fact_id)
            await repo.update_text(fact_id, new_text, new_embedding)

            extraction = await self.memory.extractor.extract(new_text)
            await self.memory._process_extraction(fact_id, extraction)

            fact = await repo.get(fact_id)

        self.channel.publish(FactUpdated(fact_id=fact_id, text=new_text))

        entity_refs = await repo.get_entity_refs(fact_id)
        return fact, [{"name": e.name, "entity_id": e.entity_id} for e in entity_refs]

    async def delete_fact(self, fact_id: int) -> dict:
        async with self.memory.transaction():
            repo = self.memory.facts

            fact = await repo.get(fact_id)
            if not fact:
                raise KeyError(f"Fact {fact_id} not found")

            entity_refs_count = await repo.count_entity_refs(fact_id)
            await repo.delete(fact_id)

        self.channel.publish(FactDeleted(fact_id=fact_id))
        return {"entity_refs": entity_refs_count}

    async def update_observation(self, observation_id: int, new_summary: str) -> Observation:
        async with self.memory.transaction():
            obs_repo = self.memory.observations

            obs = await obs_repo.get(observation_id)
            if not obs:
                raise KeyError(f"Observation {observation_id} not found")

            new_embedding = await self.memory.embedder.embed_one(new_summary)
            obs = await obs_repo.update_summary(observation_id, new_summary, new_embedding)

        return obs

    async def delete_observation(self, observation_id: int) -> None:
        async with self.memory.transaction():
            obs_repo = self.memory.observations

            obs = await obs_repo.get(observation_id)
            if not obs:
                raise KeyError(f"Observation {observation_id} not found")

            await obs_repo.delete(observation_id)
