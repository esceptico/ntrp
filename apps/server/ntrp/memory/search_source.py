from datetime import UTC, datetime

from ntrp.knowledge.models import KnowledgeObjectStatus, KnowledgeObjectType
from ntrp.knowledge.store import KnowledgeObjectRepository
from ntrp.memory.store.base import GraphDatabase
from ntrp.search.types import RawItem


class MemorySearchSource:
    name = "memory"

    def __init__(self, db: GraphDatabase):
        self.db = db

    async def scan(self) -> list[RawItem]:
        repo = KnowledgeObjectRepository(self.db.conn)
        objects = await repo.list_many(
            object_types={
                KnowledgeObjectType.FACT,
                KnowledgeObjectType.PATTERN,
                KnowledgeObjectType.LESSON,
                KnowledgeObjectType.PROCEDURE,
                KnowledgeObjectType.ARTIFACT,
            },
            statuses={KnowledgeObjectStatus.ACTIVE, KnowledgeObjectStatus.APPROVED},
            limit=10_000,
        )
        items = []
        for obj in objects:
            content = obj.text
            if obj.scope:
                content = f"{content}\n\nScope: {obj.scope}"
            created_at = _parse_dt(obj.created_at)
            updated_at = _parse_dt(obj.updated_at)
            items.append(
                RawItem(
                    source="memory",
                    source_id=f"knowledge:{obj.id}",
                    title=obj.title,
                    content=content,
                    created_at=created_at,
                    updated_at=updated_at,
                    metadata={
                        "object_type": obj.object_type.value,
                        "status": obj.status.value,
                        "scope": obj.scope,
                    },
                )
            )

        return items


def _parse_dt(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
