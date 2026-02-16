import json
from collections.abc import Sequence
from datetime import UTC, datetime

import aiosqlite

from ntrp.database import serialize_embedding
from ntrp.memory.models import Embedding, HistoryEntry, Observation

_SQL_GET_OBSERVATION = "SELECT * FROM observations WHERE id = ?"
_SQL_LIST_ALL_WITH_EMBEDDINGS = "SELECT * FROM observations WHERE embedding IS NOT NULL"
_SQL_COUNT_OBSERVATIONS = "SELECT COUNT(*) FROM observations"
_SQL_LIST_RECENT_OBSERVATIONS = "SELECT * FROM observations ORDER BY updated_at DESC LIMIT ?"
_SQL_GET_OBSERVATIONS_BY_IDS = "SELECT * FROM observations WHERE id IN ({placeholders})"

_SQL_INSERT_OBSERVATION = """
    INSERT INTO observations (
        summary, embedding, evidence_count, source_fact_ids, history,
        created_at, updated_at, last_accessed_at, access_count
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_UPDATE_OBSERVATION = """
    UPDATE observations
    SET summary = ?, embedding = ?, evidence_count = ?, source_fact_ids = ?, history = ?, updated_at = ?
    WHERE id = ?
"""

_SQL_REINFORCE_OBSERVATIONS = """
    UPDATE observations
    SET last_accessed_at = ?, access_count = access_count + 1
    WHERE id IN ({placeholders})
"""

_SQL_INSERT_OBSERVATION_VEC = "INSERT INTO observations_vec (observation_id, embedding) VALUES (?, ?)"
_SQL_DELETE_OBSERVATION_VEC = "DELETE FROM observations_vec WHERE observation_id = ?"

_SQL_SEARCH_OBSERVATIONS_VEC = """
    SELECT v.observation_id, v.distance
    FROM observations_vec v
    WHERE v.embedding MATCH ? AND k = ?
    ORDER BY v.distance
"""


def _row_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    d["source_fact_ids"] = json.loads(d["source_fact_ids"]) if d.get("source_fact_ids") else []
    d["history"] = json.loads(d["history"]) if d.get("history") else []
    return d


class ObservationRepository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def create(
        self,
        summary: str,
        embedding: Embedding | None = None,
        source_fact_id: int | None = None,
    ) -> Observation:
        now = datetime.now(UTC)
        source_fact_ids = [source_fact_id] if source_fact_id else []
        evidence_count = len(source_fact_ids)
        embedding_bytes = serialize_embedding(embedding)

        cursor = await self.conn.execute(
            _SQL_INSERT_OBSERVATION,
            (
                summary,
                embedding_bytes,
                evidence_count,
                json.dumps(source_fact_ids),
                json.dumps([]),
                now.isoformat(),
                now.isoformat(),
                now.isoformat(),
                0,
            ),
        )
        obs_id = cursor.lastrowid

        if embedding_bytes is not None:
            await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (obs_id, embedding_bytes))

        return Observation(
            id=obs_id,
            summary=summary,
            embedding=embedding,
            evidence_count=evidence_count,
            source_fact_ids=source_fact_ids,
            history=[],
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
            access_count=0,
        )

    async def get(self, observation_id: int) -> Observation | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_OBSERVATION, (observation_id,))
        return Observation.model_validate(_row_dict(rows[0])) if rows else None

    async def update(
        self,
        observation_id: int,
        summary: str,
        embedding: Embedding | None = None,
        new_fact_id: int | None = None,
        reason: str = "",
    ) -> Observation | None:
        now = datetime.now(UTC)
        obs = await self.get(observation_id)
        if not obs:
            return None

        source_fact_ids = obs.source_fact_ids.copy()
        if new_fact_id and new_fact_id not in source_fact_ids:
            source_fact_ids.append(new_fact_id)

        history = list(obs.history)
        if new_fact_id:
            history.append(
                HistoryEntry(
                    previous_text=obs.summary,
                    changed_at=now,
                    reason=reason,
                    source_fact_id=new_fact_id,
                )
            )

        evidence_count = len(source_fact_ids)

        await self.conn.execute(
            _SQL_UPDATE_OBSERVATION,
            (
                summary,
                serialize_embedding(embedding),
                evidence_count,
                json.dumps(source_fact_ids),
                json.dumps([_history_to_dict(h) for h in history]),
                now.isoformat(),
                observation_id,
            ),
        )

        if embedding is not None:
            embedding_bytes = serialize_embedding(embedding)
            await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
            await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (observation_id, embedding_bytes))

        return Observation(
            id=observation_id,
            summary=summary,
            embedding=embedding,
            evidence_count=evidence_count,
            source_fact_ids=source_fact_ids,
            history=history,
            created_at=obs.created_at,
            updated_at=now,
            last_accessed_at=obs.last_accessed_at,
            access_count=obs.access_count,
        )

    async def reinforce(self, observation_ids: Sequence[int]) -> None:
        if not observation_ids:
            return
        now = datetime.now(UTC)
        placeholders = ",".join("?" * len(observation_ids))
        await self.conn.execute(
            _SQL_REINFORCE_OBSERVATIONS.format(placeholders=placeholders),
            (now.isoformat(), *observation_ids),
        )

    async def add_source_facts(self, observation_id: int, fact_ids: list[int]) -> None:
        if not fact_ids:
            return
        existing = await self.get_fact_ids(observation_id)
        merged = existing + [fid for fid in fact_ids if fid not in existing]
        await self.conn.execute(
            "UPDATE observations SET source_fact_ids = ?, evidence_count = ? WHERE id = ?",
            (json.dumps(merged), len(merged), observation_id),
        )

    async def get_fact_ids(self, observation_id: int) -> list[int]:
        rows = await self.conn.execute_fetchall(
            "SELECT source_fact_ids FROM observations WHERE id = ?", (observation_id,)
        )
        if not rows:
            return []
        raw = rows[0]["source_fact_ids"]
        return json.loads(raw) if raw else []

    async def list_all_with_embeddings(self) -> list[Observation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_ALL_WITH_EMBEDDINGS)
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def update_summary(self, observation_id: int, summary: str, embedding: Embedding) -> Observation | None:
        now = datetime.now(UTC)
        embedding_bytes = serialize_embedding(embedding)
        await self.conn.execute(
            "UPDATE observations SET summary = ?, embedding = ?, updated_at = ? WHERE id = ?",
            (summary, embedding_bytes, now.isoformat(), observation_id),
        )
        await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
        await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (observation_id, embedding_bytes))
        return await self.get(observation_id)

    async def delete(self, observation_id: int) -> None:
        await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
        await self.conn.execute("DELETE FROM observations WHERE id = ?", (observation_id,))

    async def merge(
        self,
        keeper_id: int,
        removed_id: int,
        merged_text: str,
        embedding: "Embedding",
        reason: str = "",
    ) -> Observation | None:
        keeper = await self.get(keeper_id)
        removed = await self.get(removed_id)
        if not keeper or not removed:
            return None

        now = datetime.now(UTC)

        # Merge source fact IDs
        merged_fids = keeper.source_fact_ids.copy()
        for fid in removed.source_fact_ids:
            if fid not in merged_fids:
                merged_fids.append(fid)

        # History entry for the merge
        history = list(keeper.history)
        history.append(
            HistoryEntry(
                previous_text=keeper.summary,
                changed_at=now,
                reason=reason or f"merged with observation {removed_id}",
                source_fact_id=removed.source_fact_ids[0] if removed.source_fact_ids else 0,
                absorbed_text=removed.summary,
            )
        )

        evidence_count = len(merged_fids)
        embedding_bytes = serialize_embedding(embedding)

        await self.conn.execute(
            _SQL_UPDATE_OBSERVATION,
            (
                merged_text,
                embedding_bytes,
                evidence_count,
                json.dumps(merged_fids),
                json.dumps([_history_to_dict(h) for h in history]),
                now.isoformat(),
                keeper_id,
            ),
        )

        # Update vec table
        if embedding_bytes is not None:
            await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (keeper_id,))
            await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (keeper_id, embedding_bytes))

        # Delete the removed observation
        await self.delete(removed_id)

        return Observation(
            id=keeper_id,
            summary=merged_text,
            embedding=embedding,
            evidence_count=evidence_count,
            source_fact_ids=merged_fids,
            history=history,
            created_at=keeper.created_at,
            updated_at=now,
            last_accessed_at=keeper.last_accessed_at,
            access_count=keeper.access_count,
        )

    async def list_recent(self, limit: int = 100) -> list[Observation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_RECENT_OBSERVATIONS, (limit,))
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def count(self) -> int:
        rows = await self.conn.execute_fetchall(_SQL_COUNT_OBSERVATIONS)
        return rows[0][0]

    async def clear_all(self) -> int:
        await self.conn.execute("DELETE FROM observations_vec")
        cursor = await self.conn.execute("DELETE FROM observations")
        return cursor.rowcount

    async def list_all_with_embeddings(self) -> list[Observation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_ALL_WITH_EMBEDDINGS)
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def update_embedding(self, observation_id: int, embedding: Embedding) -> None:
        embedding_bytes = serialize_embedding(embedding)
        await self.conn.execute("UPDATE observations SET embedding = ? WHERE id = ?", (embedding_bytes, observation_id))
        await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
        await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (observation_id, embedding_bytes))

    async def search_vector(self, query_embedding: Embedding, limit: int = 10) -> list[tuple[Observation, float]]:
        query_bytes = serialize_embedding(query_embedding)
        rows = await self.conn.execute_fetchall(_SQL_SEARCH_OBSERVATIONS_VEC, (query_bytes, limit))
        if not rows:
            return []

        obs_ids = [r[0] for r in rows]
        distances = {r[0]: r[1] for r in rows}

        placeholders = ",".join("?" * len(obs_ids))
        obs_rows = await self.conn.execute_fetchall(
            _SQL_GET_OBSERVATIONS_BY_IDS.format(placeholders=placeholders), obs_ids
        )
        obs_by_id = {r["id"]: Observation.model_validate(_row_dict(r)) for r in obs_rows}

        return [(obs_by_id[oid], 1 - distances[oid]) for oid in obs_ids if oid in obs_by_id]


def _history_to_dict(h: HistoryEntry) -> dict:
    d = {
        "previous_text": h.previous_text,
        "changed_at": h.changed_at.isoformat(),
        "reason": h.reason,
        "source_fact_id": h.source_fact_id,
    }
    if h.absorbed_text is not None:
        d["absorbed_text"] = h.absorbed_text
    return d
