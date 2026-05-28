from datetime import UTC, datetime

from ntrp.memory.store.base import GraphDatabase
from ntrp.search.types import RawItem


class MemorySearchSource:
    name = "memory"

    def __init__(self, db: GraphDatabase):
        self.db = db

    async def scan(self) -> list[RawItem]:
        rows = await self.db.conn.execute_fetchall(
            """
            SELECT id, kind, content, confidence, status, scope, tags, source_refs, created_at, updated_at
            FROM memory_items
            WHERE status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 10000
            """
        )
        items = []
        for row in rows:
            content = str(row["content"])
            if row["scope"]:
                content = f"{content}\n\nScope: {row['scope']}"
            created_at = _parse_dt(str(row["created_at"]))
            updated_at = _parse_dt(str(row["updated_at"]))
            items.append(
                RawItem(
                    source="memory",
                    source_id=f"memory_item:{row['id']}",
                    title=f"{row['kind']}: {str(row['content'])[:80]}",
                    content=content,
                    created_at=created_at,
                    updated_at=updated_at,
                    metadata={
                        "kind": row["kind"],
                        "status": row["status"],
                        "scope": row["scope"],
                        "confidence": row["confidence"],
                        "tags": row["tags"],
                        "source_refs": row["source_refs"],
                    },
                )
            )

        return items


def _parse_dt(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
