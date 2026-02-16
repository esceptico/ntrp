from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.sources.models import RawItem


class MemoryIndexable:
    name = "memory"

    def __init__(self, db: GraphDatabase):
        self.db = db

    async def scan(self) -> list[RawItem]:
        repo = FactRepository(self.db.conn)
        total = await repo.count()
        if total == 0:
            return []

        facts = await repo.list_recent(limit=total)
        fact_ids = [f.id for f in facts]
        entity_map = await repo.get_entity_refs_batch(fact_ids)

        items = []
        for fact in facts:
            entity_names = [e.name for e in entity_map.get(fact.id, [])]

            content = fact.text
            if entity_names:
                content = f"{content}\n\nEntities: {', '.join(entity_names)}"

            title = entity_names[0] if entity_names else fact.text[:50]

            items.append(
                RawItem(
                    source="memory",
                    source_id=f"fact:{fact.id}",
                    title=title,
                    content=content,
                    created_at=fact.created_at,
                    updated_at=fact.created_at,
                    metadata={},
                )
            )

        return items
