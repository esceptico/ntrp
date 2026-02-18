import json
from datetime import UTC, datetime

import aiosqlite
import numpy as np

from ntrp.database import deserialize_embedding, serialize_embedding
from ntrp.memory.models import Dream, Embedding

_SQL_INSERT_DREAM = """
    INSERT INTO dreams (bridge, insight, embedding, source_fact_ids, created_at)
    VALUES (?, ?, ?, ?, ?)
"""
_SQL_GET_DREAM = "SELECT * FROM dreams WHERE id = ?"
_SQL_LIST_RECENT = "SELECT * FROM dreams ORDER BY created_at DESC LIMIT ?"
_SQL_COUNT = "SELECT COUNT(*) FROM dreams"
_SQL_DELETE = "DELETE FROM dreams WHERE id = ?"
_SQL_LAST_CREATED = "SELECT MAX(created_at) FROM dreams"
_SQL_RECENT_EMBEDDINGS = """
    SELECT id, embedding FROM dreams
    WHERE embedding IS NOT NULL
    ORDER BY created_at DESC LIMIT ?
"""


def _row_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    d["source_fact_ids"] = json.loads(d["source_fact_ids"]) if d.get("source_fact_ids") else []
    d.pop("embedding", None)
    return d


class DreamRepository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def create(
        self, bridge: str, insight: str, source_fact_ids: list[int], embedding: Embedding | None = None
    ) -> Dream:
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_INSERT_DREAM,
            (bridge, insight, serialize_embedding(embedding), json.dumps(source_fact_ids), now.isoformat()),
        )
        return Dream(
            id=cursor.lastrowid,
            bridge=bridge,
            insight=insight,
            source_fact_ids=source_fact_ids,
            created_at=now,
        )

    async def get(self, dream_id: int) -> Dream | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_DREAM, (dream_id,))
        return Dream.model_validate(_row_dict(rows[0])) if rows else None

    async def list_recent(self, limit: int = 50) -> list[Dream]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_RECENT, (limit,))
        return [Dream.model_validate(_row_dict(r)) for r in rows]

    async def count(self) -> int:
        rows = await self.conn.execute_fetchall(_SQL_COUNT)
        return rows[0][0]

    async def delete(self, dream_id: int) -> None:
        await self.conn.execute(_SQL_DELETE, (dream_id,))

    async def last_created_at(self) -> datetime | None:
        rows = await self.conn.execute_fetchall(_SQL_LAST_CREATED)
        if not rows or rows[0][0] is None:
            return None
        raw = rows[0][0]
        if isinstance(raw, str):
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        return raw

    async def recent_embeddings(self, limit: int = 100) -> list[np.ndarray]:
        rows = await self.conn.execute_fetchall(_SQL_RECENT_EMBEDDINGS, (limit,))
        result = []
        for r in rows:
            emb = deserialize_embedding(r["embedding"])
            if emb is not None:
                result.append(emb)
        return result
