import json
from collections.abc import Sequence
from datetime import UTC, datetime

import aiosqlite

from ntrp.database import BaseRepository, deserialize_embedding, serialize_embedding
from ntrp.memory.models import Embedding, HistoryEntry, Observation
from ntrp.memory.store.base import parse_datetime

_SQL_GET_OBSERVATION = "SELECT * FROM observations WHERE id = ?"
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


class ObservationRepository(BaseRepository):
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

        await self.conn.commit()

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
        return self._row_to_observation(rows[0]) if rows else None

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

        # Append new fact ID
        source_fact_ids = obs.source_fact_ids.copy()
        if new_fact_id and new_fact_id not in source_fact_ids:
            source_fact_ids.append(new_fact_id)

        # Append history entry
        history = obs.history.copy()
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

        await self.conn.commit()

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
        await self.conn.commit()

    async def get_fact_ids(self, observation_id: int) -> list[int]:
        rows = await self.conn.execute_fetchall(
            "SELECT source_fact_ids FROM observations WHERE id = ?", (observation_id,)
        )
        if not rows:
            return []
        raw = rows[0]["source_fact_ids"]
        return json.loads(raw) if raw else []

    async def list_recent(self, limit: int = 100) -> list[Observation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_RECENT_OBSERVATIONS, (limit,))
        return [self._row_to_observation(r) for r in rows]

    async def count(self) -> int:
        rows = await self.conn.execute_fetchall(_SQL_COUNT_OBSERVATIONS)
        return rows[0][0]

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
        obs_by_id = {r["id"]: self._row_to_observation(r) for r in obs_rows}

        return [(obs_by_id[oid], 1 - distances[oid]) for oid in obs_ids if oid in obs_by_id]

    def _row_to_observation(self, row: aiosqlite.Row) -> Observation:
        created_at = parse_datetime(row["created_at"])
        last_accessed_at = parse_datetime(row["last_accessed_at"]) or created_at

        source_fact_ids = json.loads(row["source_fact_ids"]) if row["source_fact_ids"] else []
        history_raw = json.loads(row["history"]) if row["history"] else []
        history = [_dict_to_history(h) for h in history_raw]

        return Observation(
            id=row["id"],
            summary=row["summary"],
            embedding=deserialize_embedding(row["embedding"]),
            evidence_count=row["evidence_count"],
            source_fact_ids=source_fact_ids,
            history=history,
            created_at=created_at,
            updated_at=parse_datetime(row["updated_at"]),
            last_accessed_at=last_accessed_at,
            access_count=row["access_count"] or 0,
        )


def _history_to_dict(h: HistoryEntry) -> dict:
    return {
        "previous_text": h.previous_text,
        "changed_at": h.changed_at.isoformat(),
        "reason": h.reason,
        "source_fact_id": h.source_fact_id,
    }


def _dict_to_history(d: dict) -> HistoryEntry:
    return HistoryEntry(
        previous_text=d["previous_text"],
        changed_at=datetime.fromisoformat(d["changed_at"]),
        reason=d["reason"],
        source_fact_id=d["source_fact_id"],
    )
