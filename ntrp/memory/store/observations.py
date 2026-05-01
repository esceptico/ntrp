import json
from collections.abc import Sequence
from datetime import UTC, datetime

import aiosqlite

from ntrp.constants import OBSERVATION_HISTORY_LIMIT
from ntrp.database import serialize_embedding
from ntrp.memory.fts import build_fts_query
from ntrp.memory.models import Embedding, HistoryEntry, Observation

_SQL_GET_OBSERVATION = "SELECT * FROM observations WHERE id = ?"
_SQL_LIST_ALL_WITH_EMBEDDINGS = "SELECT * FROM observations WHERE embedding IS NOT NULL AND archived_at IS NULL"
_SQL_COUNT_OBSERVATIONS = "SELECT COUNT(*) FROM observations"
_SQL_LIST_RECENT_OBSERVATIONS = "SELECT * FROM observations WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT ?"
_SQL_GET_OBSERVATIONS_BY_IDS = "SELECT * FROM observations WHERE id IN ({placeholders})"

_SQL_SEARCH_OBSERVATIONS_FTS = """
    SELECT o.*
    FROM observations o
    JOIN observations_fts fts ON o.id = fts.rowid
    WHERE observations_fts MATCH ? AND o.archived_at IS NULL
    ORDER BY bm25(observations_fts)
    LIMIT ?
"""

_SQL_SEARCH_OBSERVATIONS_TEMPORAL = """
    SELECT * FROM observations
    WHERE updated_at IS NOT NULL AND archived_at IS NULL
    ORDER BY ABS(julianday(updated_at) - julianday(?))
    LIMIT ?
"""

_SQL_GET_OBSERVATIONS_FOR_ENTITY = """
    SELECT DISTINCT o.*
    FROM observations o
    JOIN obs_entity_refs oer ON o.id = oer.observation_id
    WHERE oer.entity_id = ? AND o.archived_at IS NULL
    ORDER BY o.updated_at DESC
    LIMIT ?
"""

_SQL_GET_ENTITY_IDS_FOR_OBSERVATIONS = """
    SELECT DISTINCT oer.entity_id
    FROM obs_entity_refs oer
    WHERE oer.observation_id IN ({placeholders})
    AND oer.entity_id IS NOT NULL
"""

_SQL_INSERT_OBS_ENTITY_REF = """
    INSERT OR IGNORE INTO obs_entity_refs (observation_id, entity_id)
    VALUES (?, ?)
"""

_SQL_DELETE_OBS_ENTITY_REFS = "DELETE FROM obs_entity_refs WHERE observation_id = ?"

_SQL_INSERT_OBSERVATION = """
    INSERT INTO observations (
        summary, embedding, source_fact_ids, history,
        created_at, updated_at, last_accessed_at, access_count,
        created_by, policy_version
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_UPDATE_OBSERVATION = """
    UPDATE observations
    SET summary = ?, embedding = ?, source_fact_ids = ?, history = ?, updated_at = ?, policy_version = ?
    WHERE id = ?
"""

_SQL_REINFORCE_OBSERVATIONS = """
    UPDATE observations
    SET last_accessed_at = ?, access_count = access_count + 1
    WHERE id IN ({placeholders})
"""

_SQL_INSERT_OBSERVATION_VEC = "INSERT INTO observations_vec (observation_id, embedding) VALUES (?, ?)"
_SQL_DELETE_OBSERVATION_VEC = "DELETE FROM observations_vec WHERE observation_id = ?"
_SQL_INSERT_OBSERVATION_FACT = """
    INSERT OR IGNORE INTO observation_facts (observation_id, fact_id, role, created_at)
    SELECT ?, id, 'support', ? FROM facts WHERE id = ?
"""
_SQL_DELETE_OBSERVATION_FACTS = "DELETE FROM observation_facts WHERE observation_id = ?"
_SQL_DELETE_OBSERVATION_FACTS_BY_FACT = "DELETE FROM observation_facts WHERE fact_id IN ({placeholders})"

_SQL_SEARCH_OBSERVATIONS_VEC = """
    SELECT v.observation_id, v.distance
    FROM observations_vec v
    WHERE v.embedding MATCH ? AND k = ?
    ORDER BY v.distance
"""

_SQL_GET_NONEMPTY_SOURCE_FACTS = "SELECT id, source_fact_ids FROM observations WHERE source_fact_ids != '[]'"
_SQL_UPDATE_SOURCE_FACT_IDS = "UPDATE observations SET source_fact_ids = ? WHERE id = ?"
_SQL_ADD_SOURCE_FACTS = "UPDATE observations SET source_fact_ids = ? WHERE id = ?"
_SQL_GET_SOURCE_FACT_IDS = "SELECT source_fact_ids FROM observations WHERE id = ?"

_SQL_ARCHIVE_OBSERVATIONS_BATCH = "UPDATE observations SET archived_at = ? WHERE id IN ({placeholders})"
_SQL_UNARCHIVE_OBSERVATION = "UPDATE observations SET archived_at = NULL WHERE id = ?"

_SQL_LIST_ARCHIVAL_CANDIDATES_OBS = """
    SELECT * FROM observations
    WHERE archived_at IS NULL
    ORDER BY last_accessed_at ASC
    LIMIT ?
"""

_SQL_COUNT_ARCHIVED_OBS = "SELECT COUNT(*) FROM observations WHERE archived_at IS NOT NULL"
_SQL_UPDATE_SUMMARY = "UPDATE observations SET summary = ?, embedding = ?, updated_at = ? WHERE id = ?"
_SQL_DELETE_OBSERVATION = "DELETE FROM observations WHERE id = ?"
_SQL_CLEAR_OBS_ENTITY_REFS = "DELETE FROM obs_entity_refs"
_SQL_CLEAR_OBS_FACTS = "DELETE FROM observation_facts"
_SQL_CLEAR_OBS_VEC = "DELETE FROM observations_vec"
_SQL_CLEAR_OBSERVATIONS = "DELETE FROM observations"
_SQL_UPDATE_OBS_EMBEDDING = "UPDATE observations SET embedding = ? WHERE id = ?"


def _row_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    d["source_fact_ids"] = json.loads(d["source_fact_ids"]) if d.get("source_fact_ids") else []
    d["history"] = json.loads(d["history"]) if d.get("history") else []
    return d


def _filtered_observation_clauses(
    *,
    status: str,
    accessed: str | None,
    min_sources: int | None,
    max_sources: int | None,
) -> tuple[str, list[object]]:
    where = []
    params: list[object] = []

    match status:
        case "active":
            where.append("o.archived_at IS NULL")
        case "archived":
            where.append("o.archived_at IS NOT NULL")
        case "all":
            pass
        case _:
            raise ValueError(f"unsupported observation status: {status}")

    match accessed:
        case "never":
            where.append("o.access_count = 0")
        case "used":
            where.append("o.access_count > 0")
        case None:
            pass
        case _:
            raise ValueError(f"unsupported observation accessed filter: {accessed}")

    if min_sources is not None:
        where.append("COALESCE(json_array_length(o.source_fact_ids), 0) >= ?")
        params.append(min_sources)
    if max_sources is not None:
        where.append("COALESCE(json_array_length(o.source_fact_ids), 0) <= ?")
        params.append(max_sources)

    where_sql = f" WHERE {' AND '.join(where)}" if where else ""
    return where_sql, params


async def _insert_observation_fact(conn: aiosqlite.Connection, observation_id: int, fact_id: int, created_at: str) -> None:
    await conn.execute(_SQL_INSERT_OBSERVATION_FACT, (observation_id, created_at, fact_id))


class ObservationRepository:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def create(
        self,
        summary: str,
        embedding: Embedding | None = None,
        source_fact_id: int | None = None,
        created_by: str = "manual",
        policy_version: str = "manual",
    ) -> Observation:
        now = datetime.now(UTC)
        source_fact_ids = [source_fact_id] if source_fact_id else []
        embedding_bytes = serialize_embedding(embedding)

        cursor = await self.conn.execute(
            _SQL_INSERT_OBSERVATION,
            (
                summary,
                embedding_bytes,
                json.dumps(source_fact_ids),
                json.dumps([]),
                now.isoformat(),
                now.isoformat(),
                now.isoformat(),
                0,
                created_by,
                policy_version,
            ),
        )
        obs_id = cursor.lastrowid

        if embedding_bytes is not None:
            await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (obs_id, embedding_bytes))
        if source_fact_id:
            await _insert_observation_fact(self.conn, obs_id, source_fact_id, now.isoformat())

        return Observation(
            id=obs_id,
            summary=summary,
            embedding=embedding,
            source_fact_ids=source_fact_ids,
            history=[],
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
            access_count=0,
            created_by=created_by,
            policy_version=policy_version,
        )

    async def get(self, observation_id: int) -> Observation | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_OBSERVATION, (observation_id,))
        return Observation.model_validate(_row_dict(rows[0])) if rows else None

    async def get_batch(self, observation_ids: list[int]) -> dict[int, Observation]:
        if not observation_ids:
            return {}
        placeholders = ",".join("?" * len(observation_ids))
        rows = await self.conn.execute_fetchall(
            _SQL_GET_OBSERVATIONS_BY_IDS.format(placeholders=placeholders),
            observation_ids,
        )
        return {r["id"]: Observation.model_validate(_row_dict(r)) for r in rows}

    async def update(
        self,
        observation_id: int,
        summary: str,
        embedding: Embedding | None = None,
        new_fact_id: int | None = None,
        reason: str = "",
        policy_version: str = "manual",
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
            history = history[-OBSERVATION_HISTORY_LIMIT:]

        await self.conn.execute(
            _SQL_UPDATE_OBSERVATION,
            (
                summary,
                serialize_embedding(embedding),
                json.dumps(source_fact_ids),
                json.dumps([_history_to_dict(h) for h in history]),
                now.isoformat(),
                policy_version,
                observation_id,
            ),
        )

        if embedding is not None:
            embedding_bytes = serialize_embedding(embedding)
            await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
            await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (observation_id, embedding_bytes))
        if new_fact_id:
            await _insert_observation_fact(self.conn, observation_id, new_fact_id, now.isoformat())

        return Observation(
            id=observation_id,
            summary=summary,
            embedding=embedding,
            source_fact_ids=source_fact_ids,
            history=history,
            created_at=obs.created_at,
            updated_at=now,
            last_accessed_at=obs.last_accessed_at,
            access_count=obs.access_count,
            created_by=obs.created_by,
            policy_version=policy_version,
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

    async def remove_source_facts(self, fact_ids: list[int]) -> None:
        """Remove deleted fact IDs from all observations' source_fact_ids."""
        if not fact_ids:
            return
        fact_id_set = set(fact_ids)
        rows = await self.conn.execute_fetchall(_SQL_GET_NONEMPTY_SOURCE_FACTS)
        placeholders = ",".join("?" * len(fact_ids))
        await self.conn.execute(_SQL_DELETE_OBSERVATION_FACTS_BY_FACT.format(placeholders=placeholders), fact_ids)
        for row in rows:
            raw_ids = json.loads(row["source_fact_ids"]) if row["source_fact_ids"] else []
            new_ids = [fid for fid in raw_ids if fid not in fact_id_set]
            if len(new_ids) != len(raw_ids):
                await self.conn.execute(_SQL_UPDATE_SOURCE_FACT_IDS, (json.dumps(new_ids), row["id"]))

    async def add_source_facts(self, observation_id: int, fact_ids: list[int]) -> None:
        if not fact_ids:
            return
        existing = await self.get_fact_ids(observation_id)
        new_ids = [fid for fid in fact_ids if fid not in existing]
        merged = existing + new_ids
        await self.conn.execute(_SQL_ADD_SOURCE_FACTS, (json.dumps(merged), observation_id))
        now = datetime.now(UTC).isoformat()
        for fact_id in new_ids:
            await _insert_observation_fact(self.conn, observation_id, fact_id, now)

    async def get_fact_ids(self, observation_id: int) -> list[int]:
        rows = await self.conn.execute_fetchall(_SQL_GET_SOURCE_FACT_IDS, (observation_id,))
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
            _SQL_UPDATE_SUMMARY,
            (summary, embedding_bytes, now.isoformat(), observation_id),
        )
        await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
        await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (observation_id, embedding_bytes))
        return await self.get(observation_id)

    async def delete(self, observation_id: int) -> None:
        await self.conn.execute(_SQL_DELETE_OBS_ENTITY_REFS, (observation_id,))
        await self.conn.execute(_SQL_DELETE_OBSERVATION_FACTS, (observation_id,))
        await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
        await self.conn.execute(_SQL_DELETE_OBSERVATION, (observation_id,))

    async def merge(
        self,
        keeper_id: int,
        removed_id: int,
        merged_text: str,
        embedding: "Embedding",
        reason: str = "",
        policy_version: str = "memory.observation_merge.v1",
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
        history = history[-OBSERVATION_HISTORY_LIMIT:]

        embedding_bytes = serialize_embedding(embedding)

        await self.conn.execute(
            _SQL_UPDATE_OBSERVATION,
            (
                merged_text,
                embedding_bytes,
                json.dumps(merged_fids),
                json.dumps([_history_to_dict(h) for h in history]),
                now.isoformat(),
                policy_version,
                keeper_id,
            ),
        )
        await self.conn.execute(_SQL_DELETE_OBSERVATION_FACTS, (keeper_id,))
        for fact_id in merged_fids:
            await _insert_observation_fact(self.conn, keeper_id, fact_id, now.isoformat())

        # Update vec table
        if embedding_bytes is not None:
            await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (keeper_id,))
            await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (keeper_id, embedding_bytes))

        # Merge entity links from removed into keeper
        removed_entities = await self.get_entity_ids([removed_id])
        if removed_entities:
            await self.link_entities(keeper_id, removed_entities)

        # Delete the removed observation
        await self.delete(removed_id)

        return Observation(
            id=keeper_id,
            summary=merged_text,
            embedding=embedding,
            source_fact_ids=merged_fids,
            history=history,
            created_at=keeper.created_at,
            updated_at=now,
            last_accessed_at=keeper.last_accessed_at,
            access_count=keeper.access_count,
            created_by=keeper.created_by,
            policy_version=policy_version,
        )

    async def list_recent(self, limit: int = 100) -> list[Observation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_RECENT_OBSERVATIONS, (limit,))
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def list_filtered(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str = "active",
        accessed: str | None = None,
        min_sources: int | None = None,
        max_sources: int | None = None,
    ) -> tuple[list[Observation], int]:
        where_sql, params = _filtered_observation_clauses(
            status=status,
            accessed=accessed,
            min_sources=min_sources,
            max_sources=max_sources,
        )
        count_rows = await self.read_conn.execute_fetchall(
            f"SELECT COUNT(*) FROM observations o{where_sql}",
            params,
        )
        rows = await self.read_conn.execute_fetchall(
            f"SELECT o.* FROM observations o{where_sql} ORDER BY o.updated_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [Observation.model_validate(_row_dict(r)) for r in rows], count_rows[0][0]

    async def count(self) -> int:
        rows = await self.conn.execute_fetchall(_SQL_COUNT_OBSERVATIONS)
        return rows[0][0]

    async def clear_all(self) -> int:
        await self.conn.execute(_SQL_CLEAR_OBS_ENTITY_REFS)
        await self.conn.execute(_SQL_CLEAR_OBS_FACTS)
        await self.conn.execute(_SQL_CLEAR_OBS_VEC)
        cursor = await self.conn.execute(_SQL_CLEAR_OBSERVATIONS)
        return cursor.rowcount

    async def update_embedding(self, observation_id: int, embedding: Embedding) -> None:
        embedding_bytes = serialize_embedding(embedding)
        await self.conn.execute(_SQL_UPDATE_OBS_EMBEDDING, (embedding_bytes, observation_id))
        await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (observation_id,))
        await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (observation_id, embedding_bytes))

    async def search_fts(self, query: str, limit: int = 10) -> list[Observation]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        rows = await self.read_conn.execute_fetchall(_SQL_SEARCH_OBSERVATIONS_FTS, (fts_query, limit))
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def search_temporal(self, reference_time: datetime, limit: int = 10) -> list[Observation]:
        rows = await self.conn.execute_fetchall(_SQL_SEARCH_OBSERVATIONS_TEMPORAL, (reference_time.isoformat(), limit))
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def get_for_entity(self, entity_id: int, limit: int = 20) -> list[Observation]:
        rows = await self.read_conn.execute_fetchall(_SQL_GET_OBSERVATIONS_FOR_ENTITY, (entity_id, limit))
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def get_entity_ids(self, observation_ids: list[int]) -> list[int]:
        if not observation_ids:
            return []
        placeholders = ",".join("?" * len(observation_ids))
        rows = await self.conn.execute_fetchall(
            _SQL_GET_ENTITY_IDS_FOR_OBSERVATIONS.format(placeholders=placeholders),
            observation_ids,
        )
        return [r[0] for r in rows]

    async def link_entities(self, observation_id: int, entity_ids: list[int]) -> None:
        for entity_id in entity_ids:
            await self.conn.execute(_SQL_INSERT_OBS_ENTITY_REF, (observation_id, entity_id))

    async def merge_entity_refs(self, keep_id: int, merge_ids: list[int]) -> None:
        """Repoint obs_entity_refs from absorbed entity IDs to keeper."""
        if not merge_ids:
            return
        placeholders = ",".join("?" * len(merge_ids))
        # Update where possible (no conflict with existing keeper link)
        await self.conn.execute(
            f"UPDATE OR IGNORE obs_entity_refs SET entity_id = ? WHERE entity_id IN ({placeholders})",
            (keep_id, *merge_ids),
        )
        # Delete remaining rows that couldn't be updated (observation already links to keeper)
        await self.conn.execute(
            f"DELETE FROM obs_entity_refs WHERE entity_id IN ({placeholders})",
            merge_ids,
        )

    async def replace_entity_links(self, observation_id: int, entity_ids: list[int]) -> None:
        await self.conn.execute(_SQL_DELETE_OBS_ENTITY_REFS, (observation_id,))
        for entity_id in entity_ids:
            await self.conn.execute(_SQL_INSERT_OBS_ENTITY_REF, (observation_id, entity_id))

    async def search_vector(self, query_embedding: Embedding, limit: int = 10) -> list[tuple[Observation, float]]:
        query_bytes = serialize_embedding(query_embedding)
        rows = await self.read_conn.execute_fetchall(_SQL_SEARCH_OBSERVATIONS_VEC, (query_bytes, limit))
        if not rows:
            return []

        obs_ids = [r[0] for r in rows]
        distances = {r[0]: r[1] for r in rows}

        placeholders = ",".join("?" * len(obs_ids))
        obs_rows = await self.read_conn.execute_fetchall(
            _SQL_GET_OBSERVATIONS_BY_IDS.format(placeholders=placeholders), obs_ids
        )
        obs_by_id = {r["id"]: Observation.model_validate(_row_dict(r)) for r in obs_rows}

        return [
            (obs_by_id[oid], 1 - distances[oid])
            for oid in obs_ids
            if oid in obs_by_id and obs_by_id[oid].archived_at is None
        ]

    async def archive_batch(self, observation_ids: list[int]) -> int:
        if not observation_ids:
            return 0
        now = datetime.now(UTC)
        placeholders = ",".join("?" * len(observation_ids))
        await self.conn.execute(
            _SQL_ARCHIVE_OBSERVATIONS_BATCH.format(placeholders=placeholders),
            (now.isoformat(), *observation_ids),
        )
        for oid in observation_ids:
            await self.conn.execute(_SQL_DELETE_OBSERVATION_VEC, (oid,))
        return len(observation_ids)

    async def unarchive(self, observation_id: int) -> None:
        obs = await self.get(observation_id)
        if not obs:
            return
        await self.conn.execute(_SQL_UNARCHIVE_OBSERVATION, (observation_id,))
        if obs.embedding is not None:
            embedding_bytes = serialize_embedding(obs.embedding)
            await self.conn.execute(_SQL_INSERT_OBSERVATION_VEC, (observation_id, embedding_bytes))

    async def list_archival_candidates(self, limit: int = 100) -> list[Observation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_ARCHIVAL_CANDIDATES_OBS, (limit,))
        return [Observation.model_validate(_row_dict(r)) for r in rows]

    async def count_archived(self) -> int:
        rows = await self.conn.execute_fetchall(_SQL_COUNT_ARCHIVED_OBS)
        return rows[0][0] if rows else 0


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
