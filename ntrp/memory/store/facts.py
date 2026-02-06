from collections.abc import Sequence
from datetime import datetime

import aiosqlite

from ntrp.database import BaseRepository, deserialize_embedding, serialize_embedding
from ntrp.memory.models import Embedding, Entity, EntityRef, Fact, FactLink, FactType, LinkType
from ntrp.memory.store.base import parse_datetime

# --- SQL Queries ---

# Facts CRUD
_SQL_GET_FACT = "SELECT * FROM facts WHERE id = ?"
_SQL_COUNT_FACTS = "SELECT COUNT(*) FROM facts"
_SQL_LIST_RECENT = "SELECT * FROM facts ORDER BY created_at DESC LIMIT ?"
_SQL_DELETE_FACT = "DELETE FROM facts WHERE id = ?"

_SQL_INSERT_FACT = """
    INSERT INTO facts (
        text, fact_type, embedding, source_type, source_ref,
        created_at, happened_at, last_accessed_at, access_count
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_LIST_TIME_WINDOW = """
    SELECT * FROM facts
    WHERE created_at BETWEEN ? AND ?
    ORDER BY created_at DESC
"""

_SQL_LIST_UNCONSOLIDATED = """
    SELECT * FROM facts
    WHERE consolidated_at IS NULL
    ORDER BY created_at ASC
    LIMIT ?
"""

_SQL_MARK_CONSOLIDATED = "UPDATE facts SET consolidated_at = ? WHERE id = ?"

_SQL_REINFORCE_FACTS = """
    UPDATE facts
    SET last_accessed_at = ?, access_count = access_count + 1
    WHERE id IN ({placeholders})
"""

_SQL_GET_FACTS_BY_IDS = "SELECT * FROM facts WHERE id IN ({placeholders})"

# Facts vector
_SQL_INSERT_FACT_VEC = "INSERT INTO facts_vec (fact_id, embedding) VALUES (?, ?)"
_SQL_DELETE_FACT_VEC = "DELETE FROM facts_vec WHERE fact_id = ?"

_SQL_SEARCH_FACTS_VEC = """
    SELECT v.fact_id, v.distance
    FROM facts_vec v
    WHERE v.embedding MATCH ? AND k = ?
    ORDER BY v.distance
"""

_SQL_SEARCH_FACTS_FTS = """
    SELECT f.*
    FROM facts f
    JOIN facts_fts fts ON f.id = fts.rowid
    WHERE facts_fts MATCH ?
    ORDER BY bm25(facts_fts)
    LIMIT ?
"""

# Entity refs
_SQL_INSERT_ENTITY_REF = "INSERT INTO entity_refs (fact_id, name, entity_type, canonical_id) VALUES (?, ?, ?, ?)"
_SQL_GET_ENTITY_REFS = "SELECT * FROM entity_refs WHERE fact_id = ?"
_SQL_GET_ENTITY_REFS_BATCH = "SELECT * FROM entity_refs WHERE fact_id IN ({placeholders})"
_SQL_DELETE_ENTITY_REFS = "DELETE FROM entity_refs WHERE fact_id = ?"
_SQL_UPDATE_ENTITY_REFS_CANONICAL = "UPDATE entity_refs SET canonical_id = ? WHERE canonical_id IN ({placeholders})"

_SQL_GET_FACTS_FOR_ENTITY = """
    SELECT f.*
    FROM facts f
    JOIN entity_refs er ON f.id = er.fact_id
    WHERE er.name = ?
    ORDER BY f.created_at DESC
    LIMIT ?
"""

_SQL_GET_FACTS_SHARING_ENTITIES = """
    SELECT f.*, COUNT(*) as shared_count
    FROM facts f
    JOIN entity_refs er1 ON f.id = er1.fact_id
    JOIN entity_refs er2 ON er1.name = er2.name
    WHERE er2.fact_id = ? AND f.id != ?
    GROUP BY f.id
    ORDER BY shared_count DESC, f.created_at DESC
    LIMIT ?
"""

_SQL_GET_FACTS_SHARING_ENTITIES_EXCLUDE = """
    SELECT f.*, COUNT(*) as shared_count
    FROM facts f
    JOIN entity_refs er1 ON f.id = er1.fact_id
    JOIN entity_refs er2 ON er1.name = er2.name
    WHERE er2.fact_id = ? AND f.id != ?
      AND er1.name NOT IN ({placeholders})
    GROUP BY f.id
    ORDER BY shared_count DESC, f.created_at DESC
    LIMIT ?
"""

# Fact links
_SQL_DELETE_FACT_LINKS = "DELETE FROM fact_links WHERE source_fact_id = ? OR target_fact_id = ?"

_SQL_INSERT_LINK = """
    INSERT OR IGNORE INTO fact_links (
        source_fact_id, target_fact_id, link_type, weight, created_at
    )
    VALUES (?, ?, ?, ?, ?)
"""

_SQL_GET_LINKS = """
    SELECT * FROM fact_links
    WHERE source_fact_id = ? OR target_fact_id = ?
"""

_SQL_GET_LINKS_BY_TYPE = """
    SELECT * FROM fact_links
    WHERE (source_fact_id = ? OR target_fact_id = ?) AND link_type = ?
"""

# Entities CRUD
_SQL_GET_ENTITY = "SELECT * FROM entities WHERE id = ?"
_SQL_GET_ENTITY_BY_NAME = "SELECT * FROM entities WHERE name = ?"
_SQL_GET_ENTITY_BY_NAME_TYPE = "SELECT * FROM entities WHERE name = ? AND entity_type = ?"
_SQL_GET_CORE_ENTITIES = "SELECT * FROM entities WHERE is_core = TRUE"
_SQL_GET_ENTITIES_BY_IDS = "SELECT * FROM entities WHERE id IN ({placeholders})"
_SQL_DELETE_ENTITIES = "DELETE FROM entities WHERE id IN ({placeholders})"

_SQL_INSERT_ENTITY = """
    INSERT OR IGNORE INTO entities (
        name, entity_type, embedding, is_core, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
"""

_SQL_LIST_ENTITIES_BY_TYPE = """
    SELECT * FROM entities
    WHERE entity_type = ?
    ORDER BY updated_at DESC
    LIMIT ?
"""

# Entities vector
_SQL_INSERT_ENTITY_VEC = "INSERT INTO entities_vec (entity_id, embedding) VALUES (?, ?)"
_SQL_DELETE_ENTITIES_VEC = "DELETE FROM entities_vec WHERE entity_id IN ({placeholders})"

_SQL_SEARCH_ENTITIES_VEC = """
    SELECT v.entity_id, v.distance
    FROM entities_vec v
    WHERE v.embedding MATCH ? AND k = ?
    ORDER BY v.distance
"""

# Entity resolution helpers
_SQL_COUNT_ENTITY_FACTS = "SELECT COUNT(*) FROM entity_refs WHERE name = ?"

_SQL_ENTITY_CO_OCCURRENCE_SOURCES = """
    SELECT COUNT(DISTINCT f.source_ref) as shared_sources
    FROM facts f
    JOIN entity_refs er1 ON f.id = er1.fact_id
    JOIN entity_refs er2 ON f.id = er2.fact_id
    WHERE er1.name = ? AND er2.name = ?
      AND f.source_ref IS NOT NULL
"""

_SQL_ENTITY_CO_OCCURRENCE_FACTS = """
    SELECT COUNT(*) FROM (
        SELECT f.id
        FROM facts f
        JOIN entity_refs er1 ON f.id = er1.fact_id
        JOIN entity_refs er2 ON f.id = er2.fact_id
        WHERE er1.name = ? AND er2.name = ?
    )
"""

_SQL_ENTITY_LAST_MENTION = """
    SELECT f.created_at
    FROM facts f
    JOIN entity_refs er ON f.id = er.fact_id
    WHERE er.name = ?
    ORDER BY f.created_at DESC
    LIMIT 1
"""

_SQL_ENTITY_SOURCE_OVERLAP = """
    SELECT 1
    FROM facts f
    JOIN entity_refs er ON f.id = er.fact_id
    WHERE er.name = ? AND f.source_ref = ?
    LIMIT 1
"""


class FactRepository(BaseRepository):
    async def get(self, fact_id: int) -> Fact | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_FACT, (fact_id,))
        if not rows:
            return None
        fact = self._row_to_fact(rows[0])
        fact.entity_refs = await self.get_entity_refs(fact_id)
        return fact

    async def create(
        self,
        text: str,
        fact_type: FactType,
        source_type: str,
        source_ref: str | None = None,
        embedding: Embedding | None = None,
        happened_at: datetime | None = None,
    ) -> Fact:
        now = datetime.now()
        embedding_bytes = serialize_embedding(embedding)
        cursor = await self.conn.execute(
            _SQL_INSERT_FACT,
            (
                text,
                fact_type.value,
                embedding_bytes,
                source_type,
                source_ref,
                now.isoformat(),
                happened_at.isoformat() if happened_at else None,
                now.isoformat(),
                0,
            ),
        )
        fact_id = cursor.lastrowid
        if embedding_bytes:
            await self.conn.execute(_SQL_INSERT_FACT_VEC, (fact_id, embedding_bytes))
        await self.conn.commit()
        return Fact(
            id=fact_id,
            text=text,
            fact_type=fact_type,
            embedding=embedding,
            source_type=source_type,
            source_ref=source_ref,
            created_at=now,
            happened_at=happened_at,
            last_accessed_at=now,
            access_count=0,
        )

    async def reinforce(self, fact_ids: Sequence[int]) -> None:
        if not fact_ids:
            return
        now = datetime.now()
        placeholders = ",".join("?" * len(fact_ids))
        await self.conn.execute(
            _SQL_REINFORCE_FACTS.format(placeholders=placeholders),
            (now.isoformat(), *fact_ids),
        )
        await self.conn.commit()

    async def list_recent(self, limit: int = 100) -> list[Fact]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_RECENT, (limit,))
        return [self._row_to_fact(r) for r in rows]

    async def list_in_time_window(self, start: datetime, end: datetime) -> list[Fact]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_TIME_WINDOW, (start.isoformat(), end.isoformat()))
        return [self._row_to_fact(r) for r in rows]

    async def count(self) -> int:
        rows = await self.conn.execute_fetchall(_SQL_COUNT_FACTS)
        return rows[0][0]

    async def delete(self, fact_id: int) -> None:
        await self.conn.execute(_SQL_DELETE_ENTITY_REFS, (fact_id,))
        await self.conn.execute(_SQL_DELETE_FACT_LINKS, (fact_id, fact_id))
        await self.conn.execute(_SQL_DELETE_FACT_VEC, (fact_id,))
        await self.conn.execute(_SQL_DELETE_FACT, (fact_id,))
        await self.conn.commit()

    async def list_unconsolidated(self, limit: int = 100) -> list[Fact]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_UNCONSOLIDATED, (limit,))
        return [self._row_to_fact(r) for r in rows]

    async def mark_consolidated(self, fact_id: int) -> None:
        now = datetime.now()
        await self.conn.execute(_SQL_MARK_CONSOLIDATED, (now.isoformat(), fact_id))
        await self.conn.commit()

    def _row_to_fact(self, row: aiosqlite.Row) -> Fact:
        created_at = parse_datetime(row["created_at"])
        last_accessed_at = parse_datetime(row["last_accessed_at"]) or created_at
        return Fact(
            id=row["id"],
            text=row["text"],
            fact_type=FactType(row["fact_type"]),
            embedding=deserialize_embedding(row["embedding"]),
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            created_at=created_at,
            happened_at=parse_datetime(row["happened_at"]),
            last_accessed_at=last_accessed_at,
            access_count=row["access_count"] or 0,
            consolidated_at=parse_datetime(row["consolidated_at"]),
        )

    # --- Entity Refs ---

    async def add_entity_ref(
        self, fact_id: int, name: str, entity_type: str, canonical_id: int | None = None
    ) -> EntityRef:
        cursor = await self.conn.execute(_SQL_INSERT_ENTITY_REF, (fact_id, name, entity_type, canonical_id))
        await self.conn.commit()
        return EntityRef(
            id=cursor.lastrowid,
            fact_id=fact_id,
            name=name,
            entity_type=entity_type,
            canonical_id=canonical_id,
        )

    async def get_entity_refs(self, fact_id: int) -> list[EntityRef]:
        rows = await self.conn.execute_fetchall(_SQL_GET_ENTITY_REFS, (fact_id,))
        return [self._row_to_entity_ref(r) for r in rows]

    async def get_entity_refs_batch(self, fact_ids: list[int]) -> dict[int, list[EntityRef]]:
        if not fact_ids:
            return {}
        placeholders = ",".join("?" * len(fact_ids))
        rows = await self.conn.execute_fetchall(
            _SQL_GET_ENTITY_REFS_BATCH.format(placeholders=placeholders), fact_ids
        )
        result: dict[int, list[EntityRef]] = {fid: [] for fid in fact_ids}
        for r in rows:
            ref = self._row_to_entity_ref(r)
            result[ref.fact_id].append(ref)
        return result

    async def get_facts_for_entity(self, name: str, limit: int = 100) -> list[Fact]:
        rows = await self.conn.execute_fetchall(_SQL_GET_FACTS_FOR_ENTITY, (name, limit))
        return [self._row_to_fact(r) for r in rows]

    async def get_facts_sharing_entities(
        self, fact_id: int, limit: int = 50, exclude_names: set[str] | None = None
    ) -> list[tuple[Fact, int]]:
        if exclude_names:
            placeholders = ",".join("?" * len(exclude_names))
            rows = await self.conn.execute_fetchall(
                _SQL_GET_FACTS_SHARING_ENTITIES_EXCLUDE.format(placeholders=placeholders),
                (fact_id, fact_id, *exclude_names, limit),
            )
        else:
            rows = await self.conn.execute_fetchall(_SQL_GET_FACTS_SHARING_ENTITIES, (fact_id, fact_id, limit))
        return [(self._row_to_fact(r), r["shared_count"]) for r in rows]

    def _row_to_entity_ref(self, row: aiosqlite.Row) -> EntityRef:
        return EntityRef(
            id=row["id"],
            fact_id=row["fact_id"],
            name=row["name"],
            entity_type=row["entity_type"],
            canonical_id=row["canonical_id"],
        )

    # --- Fact Links ---

    async def create_link(
        self,
        source_fact_id: int,
        target_fact_id: int,
        link_type: LinkType,
        weight: float,
    ) -> FactLink:
        now = datetime.now()
        cursor = await self.conn.execute(
            _SQL_INSERT_LINK,
            (source_fact_id, target_fact_id, link_type.value, weight, now.isoformat()),
        )
        await self.conn.commit()
        return FactLink(
            id=cursor.lastrowid,
            source_fact_id=source_fact_id,
            target_fact_id=target_fact_id,
            link_type=link_type,
            weight=weight,
            created_at=now,
        )

    async def get_links(self, fact_id: int) -> list[FactLink]:
        rows = await self.conn.execute_fetchall(_SQL_GET_LINKS, (fact_id, fact_id))
        return [self._row_to_link(r) for r in rows]

    async def get_links_by_type(self, fact_id: int, link_type: LinkType) -> list[FactLink]:
        rows = await self.conn.execute_fetchall(_SQL_GET_LINKS_BY_TYPE, (fact_id, fact_id, link_type.value))
        return [self._row_to_link(r) for r in rows]

    def _row_to_link(self, row: aiosqlite.Row) -> FactLink:
        return FactLink(
            id=row["id"],
            source_fact_id=row["source_fact_id"],
            target_fact_id=row["target_fact_id"],
            link_type=LinkType(row["link_type"]),
            weight=row["weight"],
            created_at=parse_datetime(row["created_at"]),
        )

    # --- Search ---

    async def search_facts_vector(self, query_embedding: Embedding, limit: int = 10) -> list[tuple[Fact, float]]:
        query_bytes = serialize_embedding(query_embedding)
        rows = await self.conn.execute_fetchall(_SQL_SEARCH_FACTS_VEC, (query_bytes, limit))
        if not rows:
            return []

        fact_ids = [r[0] for r in rows]
        distances = {r[0]: r[1] for r in rows}

        placeholders = ",".join("?" * len(fact_ids))
        fact_rows = await self.conn.execute_fetchall(_SQL_GET_FACTS_BY_IDS.format(placeholders=placeholders), fact_ids)
        facts_by_id = {r["id"]: self._row_to_fact(r) for r in fact_rows}

        return [(facts_by_id[fid], 1 - distances[fid]) for fid in fact_ids if fid in facts_by_id]

    async def search_facts_fts(self, query: str, limit: int = 10) -> list[Fact]:
        escaped = '"' + query.replace('"', '""') + '"'
        rows = await self.conn.execute_fetchall(_SQL_SEARCH_FACTS_FTS, (escaped, limit))
        return [self._row_to_fact(r) for r in rows]

    async def search_entities_vector(self, query_embedding: Embedding, limit: int = 10) -> list[tuple[Entity, float]]:
        query_bytes = serialize_embedding(query_embedding)
        rows = await self.conn.execute_fetchall(_SQL_SEARCH_ENTITIES_VEC, (query_bytes, limit))
        if not rows:
            return []

        entity_ids = [r[0] for r in rows]
        distances = {r[0]: r[1] for r in rows}

        placeholders = ",".join("?" * len(entity_ids))
        entity_rows = await self.conn.execute_fetchall(
            _SQL_GET_ENTITIES_BY_IDS.format(placeholders=placeholders), entity_ids
        )
        entities_by_id = {r["id"]: self._row_to_entity(r) for r in entity_rows}

        return [(entities_by_id[eid], 1 - distances[eid]) for eid in entity_ids if eid in entities_by_id]

    # --- Entities ---

    async def get_entity(self, entity_id: int) -> Entity | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_ENTITY, (entity_id,))
        return self._row_to_entity(rows[0]) if rows else None

    async def get_entity_by_name(self, name: str, entity_type: str | None = None) -> Entity | None:
        if entity_type:
            rows = await self.conn.execute_fetchall(_SQL_GET_ENTITY_BY_NAME_TYPE, (name, entity_type))
        else:
            rows = await self.conn.execute_fetchall(_SQL_GET_ENTITY_BY_NAME, (name,))
        return self._row_to_entity(rows[0]) if rows else None

    async def create_entity(
        self,
        name: str,
        entity_type: str,
        embedding: Embedding | None = None,
        is_core: bool = False,
    ) -> Entity:
        now = datetime.now()
        embedding_bytes = serialize_embedding(embedding)
        cursor = await self.conn.execute(
            _SQL_INSERT_ENTITY,
            (name, entity_type, embedding_bytes, is_core, now.isoformat(), now.isoformat()),
        )
        entity_id = cursor.lastrowid

        # INSERT OR IGNORE returns 0 for lastrowid if no insert happened
        if not entity_id:
            # Entity already exists, fetch it
            existing = await self.get_entity_by_name(name, entity_type)
            if existing:
                return existing
            # Shouldn't happen, but fallback
            raise RuntimeError(f"Entity {name}/{entity_type} not found after INSERT OR IGNORE")

        if embedding_bytes:
            await self.conn.execute(_SQL_INSERT_ENTITY_VEC, (entity_id, embedding_bytes))
        await self.conn.commit()
        return Entity(
            id=entity_id,
            name=name,
            entity_type=entity_type,
            embedding=embedding,
            is_core=is_core,
            created_at=now,
            updated_at=now,
        )

    async def get_core_entities(self) -> list[Entity]:
        rows = await self.conn.execute_fetchall(_SQL_GET_CORE_ENTITIES)
        return [self._row_to_entity(r) for r in rows]

    def _row_to_entity(self, row: aiosqlite.Row) -> Entity:
        return Entity(
            id=row["id"],
            name=row["name"],
            entity_type=row["entity_type"],
            embedding=deserialize_embedding(row["embedding"]),
            is_core=bool(row["is_core"]),
            created_at=parse_datetime(row["created_at"]),
            updated_at=parse_datetime(row["updated_at"]),
        )

    async def list_entities_by_type(self, entity_type: str, limit: int = 100) -> list[Entity]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_ENTITIES_BY_TYPE, (entity_type, limit))
        return [self._row_to_entity(r) for r in rows]

    async def get_entity_co_occurrence(self, name1: str, name2: str) -> tuple[int, int]:
        rows = await self.conn.execute_fetchall(_SQL_ENTITY_CO_OCCURRENCE_SOURCES, (name1, name2))
        shared_sources = rows[0][0] if rows else 0

        rows = await self.conn.execute_fetchall(_SQL_ENTITY_CO_OCCURRENCE_FACTS, (name1, name2))
        shared_facts = rows[0][0] if rows else 0

        return shared_sources, shared_facts

    async def get_entity_last_mention(self, name: str) -> datetime | None:
        rows = await self.conn.execute_fetchall(_SQL_ENTITY_LAST_MENTION, (name,))
        return parse_datetime(rows[0][0]) if rows else None

    async def count_entity_facts(self, entity_name: str) -> int:
        rows = await self.conn.execute_fetchall(_SQL_COUNT_ENTITY_FACTS, (entity_name,))
        return rows[0][0] if rows else 0

    async def get_entity_source_overlap(self, entity_name: str, source_ref: str) -> bool:
        rows = await self.conn.execute_fetchall(_SQL_ENTITY_SOURCE_OVERLAP, (entity_name, source_ref))
        return len(rows) > 0

    async def merge_entities(self, keep_id: int, merge_ids: list[int]) -> int:
        if not merge_ids:
            return 0

        placeholders = ",".join("?" * len(merge_ids))

        await self.conn.execute(
            _SQL_UPDATE_ENTITY_REFS_CANONICAL.format(placeholders=placeholders),
            (keep_id, *merge_ids),
        )
        await self.conn.execute(_SQL_DELETE_ENTITIES_VEC.format(placeholders=placeholders), merge_ids)
        cursor = await self.conn.execute(_SQL_DELETE_ENTITIES.format(placeholders=placeholders), merge_ids)

        await self.conn.commit()
        return cursor.rowcount
