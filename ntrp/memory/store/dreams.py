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

_SQL_GET_NONEMPTY_DREAM_SOURCES = "SELECT id, source_fact_ids FROM dreams WHERE source_fact_ids != '[]'"
_SQL_UPDATE_DREAM_SOURCES = "UPDATE dreams SET source_fact_ids = ? WHERE id = ?"
_SQL_INSERT_DREAM_FACT = """
    INSERT OR IGNORE INTO dream_facts (dream_id, fact_id, role, created_at)
    SELECT ?, id, 'support', ? FROM facts WHERE id = ?
"""
_SQL_DELETE_DREAM_FACTS = "DELETE FROM dream_facts WHERE dream_id = ?"
_SQL_DELETE_DREAM_FACTS_BY_FACT = "DELETE FROM dream_facts WHERE fact_id IN ({placeholders})"


def _row_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    d["source_fact_ids"] = json.loads(d["source_fact_ids"]) if d.get("source_fact_ids") else []
    d.pop("embedding", None)
    return d


async def _insert_dream_fact(conn: aiosqlite.Connection, dream_id: int, fact_id: int, created_at: str) -> None:
    await conn.execute(_SQL_INSERT_DREAM_FACT, (dream_id, created_at, fact_id))


class DreamRepository:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def create(
        self, bridge: str, insight: str, source_fact_ids: list[int], embedding: Embedding | None = None
    ) -> Dream:
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_INSERT_DREAM,
            (bridge, insight, serialize_embedding(embedding), json.dumps(source_fact_ids), now.isoformat()),
        )
        dream_id = cursor.lastrowid
        for fact_id in source_fact_ids:
            await _insert_dream_fact(self.conn, dream_id, fact_id, now.isoformat())
        return Dream(
            id=dream_id,
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
        await self.conn.execute(_SQL_DELETE_DREAM_FACTS, (dream_id,))
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

    async def remove_source_facts(self, fact_ids: list[int]) -> None:
        if not fact_ids:
            return
        fact_id_set = set(fact_ids)
        placeholders = ",".join("?" * len(fact_ids))
        await self.conn.execute(_SQL_DELETE_DREAM_FACTS_BY_FACT.format(placeholders=placeholders), fact_ids)
        rows = await self.conn.execute_fetchall(_SQL_GET_NONEMPTY_DREAM_SOURCES)
        for row in rows:
            raw_ids = json.loads(row["source_fact_ids"]) if row["source_fact_ids"] else []
            new_ids = [fid for fid in raw_ids if fid not in fact_id_set]
            if len(new_ids) != len(raw_ids):
                await self.conn.execute(_SQL_UPDATE_DREAM_SOURCES, (json.dumps(new_ids), row["id"]))

    async def recent_embeddings(self, limit: int = 100) -> list[np.ndarray]:
        rows = await self.conn.execute_fetchall(_SQL_RECENT_EMBEDDINGS, (limit,))
        result = []
        for r in rows:
            emb = deserialize_embedding(r["embedding"])
            if emb is not None:
                result.append(emb)
        return result
