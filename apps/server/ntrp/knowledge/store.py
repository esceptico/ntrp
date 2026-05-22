from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from re import findall, fullmatch
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite

from ntrp.database import serialize_embedding
from ntrp.knowledge.entity_extraction import EntityResolutionResult, ResolvedEntity, canonical_key
from ntrp.knowledge.models import (
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
)
from ntrp.memory.models import Embedding


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def _row_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


def _object_from_row(row: aiosqlite.Row) -> KnowledgeObject:
    data = _row_dict(row)
    data["source_ids"] = json.loads(data["source_ids"] or "[]")
    data["metadata"] = json.loads(data["metadata"] or "{}")
    return KnowledgeObject.model_validate(data)


def _query_terms(query: str) -> set[str]:
    return {term for term in findall(r"[a-zA-Z0-9_]+", query.lower()) if len(term) > 2}


def _candidate_entity_names(query: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    raw = query.strip()
    # Preserve explicitly supplied entity names even when they are lowercase
    # project/product names or topic-like labels. Broader natural-language
    # questions still fall through to phrase/term extraction.
    if 1 <= len(raw.split()) <= 6 and fullmatch(r"[A-Za-z0-9_.+-]+(?:\s+[A-Za-z0-9_.+-]+)*", raw):
        key = raw.casefold()
        if len(raw) > 2:
            names.append(raw)
            seen.add(key)
    # Preserve explicit capitalized phrases like "Prime Intellect" and "Trigger.dev"-ish terms.
    for match in findall(r"(?:[A-Z][\w.-]+)(?:\s+[A-Z][\w.-]+)*", query):
        value = match.strip()
        key = value.casefold()
        if len(value) > 2 and key not in seen:
            names.append(value)
            seen.add(key)
    for term in _query_terms(query):
        if term not in seen:
            names.append(term)
            seen.add(term)
    return names[:12]


def _temporal_window(query: str) -> tuple[str, str] | None:
    lowered = query.lower()
    now = datetime.now(UTC)
    if any(term in lowered for term in ("today", "tonight")):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.isoformat(), now.isoformat()
    if "yesterday" in lowered:
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        return start.isoformat(), end.isoformat()
    if any(term in lowered for term in ("recent", "latest", "current", "lately", "last week", "this week")):
        return (now - timedelta(days=14)).isoformat(), now.isoformat()
    if any(term in lowered for term in ("last month", "this month")):
        return (now - timedelta(days=45)).isoformat(), now.isoformat()
    return None


def _fts_query(query: str) -> str | None:
    terms = [term for term in findall(r"[a-zA-Z0-9_]+", query.lower()) if len(term) > 2]
    if not terms:
        return None
    # Quote terms to avoid FTS syntax surprises from user text; OR keeps recall high
    # and the activation reranker handles precision.
    return " OR ".join(f'"{term}"' for term in terms[:32])


_SQL_SEARCH_KNOWLEDGE_OBJECTS_VEC = """
    SELECT v.knowledge_object_id, v.distance
    FROM knowledge_objects_vec v
    WHERE v.embedding MATCH ? AND k = ?
    ORDER BY v.distance
"""

_SQL_UPDATE_KNOWLEDGE_OBJECT_EMBEDDING = "UPDATE knowledge_objects SET embedding = ? WHERE id = ?"
_SQL_DELETE_KNOWLEDGE_OBJECT_VEC = "DELETE FROM knowledge_objects_vec WHERE knowledge_object_id = ?"
_SQL_INSERT_KNOWLEDGE_OBJECT_VEC = "INSERT INTO knowledge_objects_vec (knowledge_object_id, embedding) VALUES (?, ?)"
_SQL_INSERT_ENTITY = "INSERT OR IGNORE INTO entities (name, created_at, updated_at) VALUES (?, ?, ?)"
_SQL_GET_ENTITY_ID_BY_NAME = "SELECT id FROM entities WHERE name = ? COLLATE NOCASE"
_SQL_DELETE_KNOWLEDGE_ENTITY_REFS = "DELETE FROM knowledge_entity_refs WHERE knowledge_object_id = ?"
_SQL_INSERT_KNOWLEDGE_ENTITY_REF = """
    INSERT OR IGNORE INTO knowledge_entity_refs (knowledge_object_id, entity_id, name, created_at)
    VALUES (?, ?, ?, ?)
"""
_SQL_GET_KNOWLEDGE_ENTITY_NAMES = """
    SELECT ker.name
    FROM knowledge_entity_refs ker
    JOIN entities e ON e.id = ker.entity_id
    WHERE ker.knowledge_object_id = ?
    ORDER BY ker.name COLLATE NOCASE
"""


class KnowledgeObjectRepository:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def create(self, payload: KnowledgeObjectCreate) -> KnowledgeObject:
        now = datetime.now(UTC).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO knowledge_objects (
                object_type, title, text, status, scope, activation, proactiveness_level,
                score, source_ids, metadata, created_at, updated_at, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.object_type.value,
                payload.title,
                payload.text,
                payload.status.value,
                payload.scope,
                payload.activation,
                payload.proactiveness_level,
                payload.score,
                _json(payload.source_ids),
                _json(payload.metadata),
                now,
                now,
                now if payload.status in {KnowledgeObjectStatus.APPROVED, KnowledgeObjectStatus.REJECTED} else None,
            ),
        )
        await self.conn.commit()
        created = await self.get(int(cursor.lastrowid))
        if created is None:
            raise RuntimeError("knowledge object disappeared after create")
        return created

    async def get(self, object_id: int) -> KnowledgeObject | None:
        rows = await self.read_conn.execute_fetchall("SELECT * FROM knowledge_objects WHERE id = ?", (object_id,))
        return _object_from_row(rows[0]) if rows else None

    async def get_by_source_id(
        self,
        source_id: str,
        object_type: KnowledgeObjectType | None = None,
    ) -> KnowledgeObject | None:
        type_clause = "AND ko.object_type = ?" if object_type is not None else ""
        params: tuple[object, ...] = (source_id, object_type.value) if object_type is not None else (source_id,)
        rows = await self.read_conn.execute_fetchall(
            f"""
            SELECT ko.*
            FROM knowledge_objects ko, json_each(ko.source_ids) source
            WHERE source.value = ?
              {type_clause}
            ORDER BY ko.updated_at DESC, ko.id DESC
            LIMIT 1
            """,
            params,
        )
        return _object_from_row(rows[0]) if rows else None

    async def get_batch(self, object_ids: list[int]) -> dict[int, KnowledgeObject]:
        if not object_ids:
            return {}
        placeholders = ",".join("?" for _ in object_ids)
        rows = await self.read_conn.execute_fetchall(
            f"SELECT * FROM knowledge_objects WHERE id IN ({placeholders})",
            tuple(object_ids),
        )
        objects = [_object_from_row(row) for row in rows]
        return {obj.id: obj for obj in objects}

    async def list(
        self,
        *,
        object_type: KnowledgeObjectType | None = None,
        status: KnowledgeObjectStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeObject]:
        clauses: list[str] = []
        params: list[object] = []
        if object_type is not None:
            clauses.append("object_type = ?")
            params.append(object_type.value)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self.read_conn.execute_fetchall(
            f"""
            SELECT * FROM knowledge_objects
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return [_object_from_row(row) for row in rows]

    async def list_many(
        self,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[KnowledgeObject]:
        clauses: list[str] = []
        params: list[object] = []
        if object_types:
            placeholders = ",".join("?" for _ in object_types)
            clauses.append(f"object_type IN ({placeholders})")
            params.extend(sorted(item.value for item in object_types))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(sorted(item.value for item in statuses))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self.read_conn.execute_fetchall(
            f"""
            SELECT * FROM knowledge_objects
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return [_object_from_row(row) for row in rows]

    async def search_text(
        self,
        query: str,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[KnowledgeObject]:
        match = _fts_query(query)
        if not match:
            return await self.list_many(object_types=object_types, statuses=statuses, limit=limit, offset=offset)

        clauses = ["knowledge_objects_fts MATCH ?"]
        params: list[object] = [match]
        if object_types:
            placeholders = ",".join("?" for _ in object_types)
            clauses.append(f"ko.object_type IN ({placeholders})")
            params.extend(sorted(item.value for item in object_types))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"ko.status IN ({placeholders})")
            params.extend(sorted(item.value for item in statuses))
        where = " AND ".join(clauses)
        try:
            rows = await self.read_conn.execute_fetchall(
                f"""
                SELECT ko.*
                FROM knowledge_objects_fts
                JOIN knowledge_objects ko ON ko.id = knowledge_objects_fts.rowid
                WHERE {where}
                ORDER BY bm25(knowledge_objects_fts), ko.updated_at DESC, ko.id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )
        except Exception:
            return await self.list_many(object_types=object_types, statuses=statuses, limit=limit, offset=offset)
        return [_object_from_row(row) for row in rows]

    async def search_vector(
        self,
        query_embedding: Embedding,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
    ) -> list[tuple[KnowledgeObject, float]]:
        query_bytes = serialize_embedding(query_embedding)
        search_limit = limit if not (object_types or statuses) else max(limit * 10, limit)
        try:
            rows = await self.read_conn.execute_fetchall(_SQL_SEARCH_KNOWLEDGE_OBJECTS_VEC, (query_bytes, search_limit))
        except Exception:
            return []
        if not rows:
            return []
        object_ids = [int(row[0]) for row in rows]
        distances = {int(row[0]): float(row[1]) for row in rows}
        objects_by_id = await self.get_batch(object_ids)
        results: list[tuple[KnowledgeObject, float]] = []
        for object_id in object_ids:
            obj = objects_by_id.get(object_id)
            if obj is None:
                continue
            if object_types and obj.object_type not in object_types:
                continue
            if statuses and obj.status not in statuses:
                continue
            results.append((obj, 1.0 - distances[object_id]))
            if len(results) >= limit:
                break
        return results

    async def search_entities(
        self,
        query: str,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
    ) -> list[KnowledgeObject]:
        names = _candidate_entity_names(query)
        if not names:
            return []
        entity_clauses: list[str] = []
        params: list[object] = []
        for name in names:
            entity_clauses.append(
                """EXISTS (
                    SELECT 1
                    FROM knowledge_entity_refs ker
                    JOIN entities ent ON ent.id = ker.entity_id
                    WHERE ker.knowledge_object_id = ko.id
                      AND (ent.name = ? COLLATE NOCASE OR ker.name = ? COLLATE NOCASE)
                )"""
            )
            entity_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(ko.metadata, '$.entities') e WHERE e.value = ? COLLATE NOCASE)"
            )
            entity_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(ko.metadata, '$.entity_graph.entities') e WHERE e.value = ? COLLATE NOCASE)"
            )
            entity_clauses.append(
                """EXISTS (
                    SELECT 1
                    FROM knowledge_entity_refs ker_alias
                    JOIN entity_aliases ea ON ea.entity_id = ker_alias.entity_id
                    WHERE ker_alias.knowledge_object_id = ko.id
                      AND ea.status = 'active'
                      AND ea.normalized_alias = ? COLLATE NOCASE
                )"""
            )
            entity_clauses.append(
                "EXISTS (SELECT 1 FROM json_tree(ko.metadata, '$.entity_graph.aliases') a WHERE a.type = 'text' AND a.value = ? COLLATE NOCASE)"
            )
            entity_clauses.append("EXISTS (SELECT 1 FROM json_each(ko.source_ids) s WHERE s.value = ? COLLATE NOCASE)")
            params.extend([name, name, name, name, canonical_key(name), name, name])
        clauses = [f"({' OR '.join(entity_clauses)})"]
        if object_types:
            placeholders = ",".join("?" for _ in object_types)
            clauses.append(f"ko.object_type IN ({placeholders})")
            params.extend(sorted(item.value for item in object_types))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"ko.status IN ({placeholders})")
            params.extend(sorted(item.value for item in statuses))
        rows = await self.read_conn.execute_fetchall(
            f"""
            SELECT ko.*
            FROM knowledge_objects ko
            WHERE {' AND '.join(clauses)}
            ORDER BY ko.score DESC, ko.updated_at DESC, ko.id DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return [_object_from_row(row) for row in rows]

    async def search_temporal(
        self,
        query: str,
        *,
        object_types: set[KnowledgeObjectType] | None = None,
        statuses: set[KnowledgeObjectStatus] | None = None,
        limit: int = 500,
    ) -> list[KnowledgeObject]:
        window = _temporal_window(query)
        if window is None:
            return []
        start, end = window
        clauses = [
            "COALESCE(json_extract(ko.metadata, '$.happened_at'), json_extract(ko.metadata, '$.verified_at'), ko.updated_at, ko.created_at) BETWEEN ? AND ?"
        ]
        params: list[object] = [start, end]
        if object_types:
            placeholders = ",".join("?" for _ in object_types)
            clauses.append(f"ko.object_type IN ({placeholders})")
            params.extend(sorted(item.value for item in object_types))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"ko.status IN ({placeholders})")
            params.extend(sorted(item.value for item in statuses))
        rows = await self.read_conn.execute_fetchall(
            f"""
            SELECT ko.*
            FROM knowledge_objects ko
            WHERE {' AND '.join(clauses)}
            ORDER BY COALESCE(json_extract(ko.metadata, '$.happened_at'), json_extract(ko.metadata, '$.verified_at'), ko.updated_at, ko.created_at) DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return [_object_from_row(row) for row in rows]

    async def replace_entity_refs(self, object_id: int, entity_names: list[str]) -> None:
        names = list(dict.fromkeys(name.strip() for name in entity_names if name.strip()))
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(_SQL_DELETE_KNOWLEDGE_ENTITY_REFS, (object_id,))
        for name in names:
            await self.conn.execute(_SQL_INSERT_ENTITY, (name, now, now))
            rows = await self.conn.execute_fetchall(_SQL_GET_ENTITY_ID_BY_NAME, (name,))
            if rows:
                await self.conn.execute(_SQL_INSERT_KNOWLEDGE_ENTITY_REF, (object_id, int(rows[0][0]), name, now))
        await self.conn.commit()

    async def get_entity_names(self, object_id: int) -> list[str]:
        rows = await self.read_conn.execute_fetchall(_SQL_GET_KNOWLEDGE_ENTITY_NAMES, (object_id,))
        return [str(row[0]) for row in rows]

    async def list_profile_entity_names(self, *, limit: int = 100) -> list[str]:
        rows = await self.read_conn.execute_fetchall(
            """
            WITH evidence AS (
                SELECT ker.name AS name, COUNT(*) AS evidence_count, MAX(ko.updated_at) AS last_seen
                FROM knowledge_entity_refs ker
                JOIN knowledge_objects ko ON ko.id = ker.knowledge_object_id
                WHERE ko.status IN ('active', 'approved')
                  AND ko.object_type IN ('fact', 'pattern', 'lesson', 'procedure')
                  AND ker.name IS NOT NULL
                  AND TRIM(ker.name) != ''
                GROUP BY ker.name COLLATE NOCASE
            ), active_profiles AS (
                SELECT json_extract(metadata, '$.profile_entity') AS name,
                       MAX(COALESCE(json_extract(metadata, '$.valid_as_of'), updated_at)) AS valid_as_of
                FROM knowledge_objects
                WHERE object_type = 'entity_profile'
                  AND status IN ('active', 'approved')
                  AND json_extract(metadata, '$.profile_entity') IS NOT NULL
                GROUP BY json_extract(metadata, '$.profile_entity') COLLATE NOCASE
            )
            SELECT evidence.name AS name, evidence.evidence_count AS evidence_count, evidence.last_seen AS last_seen
            FROM evidence
            LEFT JOIN active_profiles ON active_profiles.name = evidence.name COLLATE NOCASE
            WHERE active_profiles.name IS NULL OR evidence.last_seen > active_profiles.valid_as_of
            ORDER BY evidence_count DESC, last_seen DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [str(row["name"]) for row in rows]

    async def get_entity_profile(self, entity_name: str) -> KnowledgeObject | None:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT * FROM knowledge_objects
            WHERE object_type = 'entity_profile'
              AND json_extract(metadata, '$.profile_entity') = ? COLLATE NOCASE
              AND status NOT IN ('archived', 'rejected', 'superseded')
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (entity_name,),
        )
        return _object_from_row(rows[0]) if rows else None

    async def _get_or_create_entity(self, entity: ResolvedEntity) -> int:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            _SQL_INSERT_ENTITY,
            (entity.name, now, now),
        )
        await self.conn.execute(
            """
            UPDATE entities
            SET entity_type = CASE WHEN entity_type = 'other' THEN ? ELSE entity_type END,
                updated_at = ?
            WHERE name = ? COLLATE NOCASE
            """,
            (entity.entity_type, now, entity.name),
        )
        rows = await self.conn.execute_fetchall(_SQL_GET_ENTITY_ID_BY_NAME, (entity.name,))
        if not rows:
            raise RuntimeError(f"entity {entity.name!r} disappeared after upsert")
        return int(rows[0][0])

    async def _alias_candidates(self, aliases: list[str], entity_type: str = "other") -> list[aiosqlite.Row]:
        keys = [canonical_key(alias) for alias in aliases if alias.strip()]
        if not keys:
            return []
        placeholders = ",".join("?" for _ in keys)
        type_clause = "AND (e.entity_type = ? OR e.entity_type = 'other' OR ? = 'other')"
        return await self.conn.execute_fetchall(
            f"""
            SELECT DISTINCT e.id, e.name, e.entity_type, ea.normalized_alias
            FROM entity_aliases ea
            JOIN entities e ON e.id = ea.entity_id
            WHERE ea.status = 'active'
              AND e.lifecycle_status = 'active'
              AND ea.normalized_alias IN ({placeholders})
              {type_clause}
            ORDER BY e.id
            """,
            (*keys, entity_type, entity_type),
        )

    async def _insert_alias(
        self,
        entity_id: int,
        alias: str,
        *,
        alias_type: str = "extracted",
        source_mention_id: int | None = None,
        confidence: float = 0.0,
        scope: str | None = None,
    ) -> None:
        cleaned = alias.strip()
        if not cleaned:
            return
        key = canonical_key(cleaned)
        existing = await self.conn.execute_fetchall(
            """
            SELECT id FROM entity_aliases
            WHERE entity_id = ? AND normalized_alias = ? AND alias_type = ? AND status = 'active'
            LIMIT 1
            """,
            (entity_id, key, alias_type),
        )
        now = datetime.now(UTC).isoformat()
        if existing:
            await self.conn.execute(
                "UPDATE entity_aliases SET confidence = MAX(confidence, ?), updated_at = ? WHERE id = ?",
                (confidence, now, int(existing[0][0])),
            )
            return
        await self.conn.execute(
            """
            INSERT INTO entity_aliases (
                entity_id, alias_text, normalized_alias, alias_type, source_mention_id,
                confidence, scope, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (entity_id, cleaned, key, alias_type, source_mention_id, confidence, scope, now, now),
        )

    async def _insert_mention(
        self,
        object_id: int,
        *,
        entity_id: int | None,
        surface: str,
        canonical_name: str | None,
        entity_type: str,
        extraction_confidence: float,
        resolution_confidence: float | None,
        resolution_status: str,
        extractor: str,
        evidence_quote: str | None = None,
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO entity_mentions (
                knowledge_object_id, entity_id, surface_text, normalized_surface, canonical_name,
                entity_type_hint, evidence_quote, extraction_confidence, resolution_confidence,
                resolution_status, extractor, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'extractor', ?)
            """,
            (
                object_id,
                entity_id,
                surface,
                canonical_key(surface),
                canonical_name,
                entity_type,
                evidence_quote,
                extraction_confidence,
                resolution_confidence,
                resolution_status,
                extractor,
                datetime.now(UTC).isoformat(),
            ),
        )
        return int(cursor.lastrowid)

    async def _insert_candidate(
        self,
        mention_id: int,
        candidate_entity_id: int | None,
        *,
        method: str,
        score: float,
        features: dict[str, object] | None = None,
        rank: int | None = None,
        decision_status: str = "proposed",
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO entity_resolution_candidates (
                mention_id, candidate_entity_id, method, score, features, rank, decision_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mention_id,
                candidate_entity_id,
                method,
                score,
                _json(features or {}),
                rank,
                decision_status,
                datetime.now(UTC).isoformat(),
            ),
        )

    async def replace_entity_resolution(
        self,
        object_id: int,
        result: EntityResolutionResult,
        *,
        extra_entity_names: list[str] | None = None,
        scope: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(_SQL_DELETE_KNOWLEDGE_ENTITY_REFS, (object_id,))
        await self.conn.execute("DELETE FROM entity_mentions WHERE knowledge_object_id = ?", (object_id,))

        for entity in result.entities:
            aliases = [entity.name, *entity.aliases, *entity.mentions]
            raw_candidates = await self._alias_candidates(aliases, entity.entity_type)
            candidates = []
            seen_candidate_ids: set[int] = set()
            for row in raw_candidates:
                candidate_id = int(row["id"])
                if candidate_id in seen_candidate_ids:
                    continue
                seen_candidate_ids.add(candidate_id)
                candidates.append(row)
            exact = [row for row in candidates if str(row["name"]).casefold() == entity.name.casefold()]
            if exact:
                entity_id = int(exact[0]["id"])
                method = "exact_name"
                score = 1.0
                status = "accepted"
            elif len(candidates) == 1:
                entity_id = int(candidates[0]["id"])
                method = "exact_alias"
                score = 0.96
                status = "accepted"
            elif len(candidates) > 1:
                for index, surface in enumerate(entity.mentions or (entity.name,)):
                    mention_id = await self._insert_mention(
                        object_id,
                        entity_id=None,
                        surface=surface,
                        canonical_name=entity.name,
                        entity_type=entity.entity_type,
                        extraction_confidence=entity.confidence,
                        resolution_confidence=None,
                        resolution_status="ambiguous",
                        extractor=result.extractor,
                    )
                    for rank, row in enumerate(candidates, start=1):
                        await self._insert_candidate(
                            mention_id,
                            int(row["id"]),
                            method="alias_collision",
                            score=0.5,
                            features={"candidate_name": row["name"], "candidate_type": row["entity_type"]},
                            rank=rank,
                            decision_status="needs_review",
                        )
                    if index == 0:
                        await self.add_identity_edge(
                            int(candidates[0]["id"]),
                            int(candidates[1]["id"]),
                            relation="possible_same_as",
                            confidence=0.5,
                            evidence={"reason": "alias_collision", "surface": surface, "object_id": object_id},
                            status="needs_review",
                            commit=False,
                        )
                continue
            else:
                entity_id = await self._get_or_create_entity(entity)
                method = "new_entity"
                score = entity.confidence
                status = "accepted"

            await self.conn.execute(_SQL_INSERT_KNOWLEDGE_ENTITY_REF, (object_id, entity_id, entity.name, now))
            source_mention_id: int | None = None
            for index, surface in enumerate(entity.mentions or (entity.name,)):
                mention_id = await self._insert_mention(
                    object_id,
                    entity_id=entity_id,
                    surface=surface,
                    canonical_name=entity.name,
                    entity_type=entity.entity_type,
                    extraction_confidence=entity.confidence,
                    resolution_confidence=score,
                    resolution_status="resolved",
                    extractor=result.extractor,
                )
                if source_mention_id is None:
                    source_mention_id = mention_id
                await self._insert_candidate(
                    mention_id,
                    entity_id,
                    method=method,
                    score=score,
                    features={"canonical_name": entity.name},
                    rank=1,
                    decision_status=status,
                )
                if index == 0:
                    await self._insert_alias(
                        entity_id,
                        entity.name,
                        alias_type="canonical",
                        source_mention_id=mention_id,
                        confidence=1.0,
                        scope=scope,
                    )
            for alias in entity.aliases:
                await self._insert_alias(
                    entity_id,
                    alias,
                    alias_type="extracted",
                    source_mention_id=source_mention_id,
                    confidence=entity.confidence,
                    scope=scope,
                )

        for item in result.unresolved:
            surface = str(item.get("surface") or item.get("canonical_name") or "unresolved")
            mention_id = await self._insert_mention(
                object_id,
                entity_id=None,
                surface=surface,
                canonical_name=str(item.get("canonical_name")) if item.get("canonical_name") else None,
                entity_type="other",
                extraction_confidence=float(item.get("confidence") or 0.0),
                resolution_confidence=None,
                resolution_status=str(item.get("resolution") or "unresolved"),
                extractor=result.extractor,
            )
            for rank, candidate_name in enumerate(item.get("candidates", []) or [], start=1):
                await self._insert_candidate(
                    mention_id,
                    None,
                    method="llm_ambiguity_candidate",
                    score=0.0,
                    features={"candidate_name": candidate_name},
                    rank=rank,
                    decision_status="needs_review",
                )

        for name in extra_entity_names or []:
            if not name.strip() or name in result.names:
                continue
            entity = ResolvedEntity(name=name.strip(), entity_type="other", confidence=1.0, mentions=(name.strip(),))
            entity_id = await self._get_or_create_entity(entity)
            await self.conn.execute(_SQL_INSERT_KNOWLEDGE_ENTITY_REF, (object_id, entity_id, entity.name, now))
            await self._insert_alias(entity_id, entity.name, alias_type="manual", confidence=1.0, scope=scope)

        await self.conn.commit()

    async def add_identity_edge(
        self,
        entity_a_id: int,
        entity_b_id: int,
        *,
        relation: str,
        confidence: float,
        evidence: dict[str, object] | None = None,
        status: str = "active",
        commit: bool = True,
    ) -> int:
        if entity_a_id == entity_b_id:
            raise ValueError("identity edge endpoints must differ")
        commit_id: int | None = None
        if commit:
            commit_id = await self._insert_resolution_commit(
                action="identity_edge",
                before_entity_ids=[entity_a_id, entity_b_id],
                after_entity_ids=[entity_a_id, entity_b_id],
                evidence=evidence or {},
                reversible_patch={},
                confidence=confidence,
            )
        cursor = await self.conn.execute(
            """
            INSERT INTO entity_identity_edges (
                entity_a_id, entity_b_id, relation, confidence, evidence, status, commit_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                min(entity_a_id, entity_b_id),
                max(entity_a_id, entity_b_id),
                relation,
                confidence,
                _json(evidence or {}),
                status,
                commit_id,
                datetime.now(UTC).isoformat(),
            ),
        )
        if commit:
            await self.conn.commit()
        return int(cursor.lastrowid)

    async def _insert_resolution_commit(
        self,
        *,
        action: str,
        before_entity_ids: list[int],
        after_entity_ids: list[int],
        evidence: dict[str, object],
        reversible_patch: dict[str, object],
        confidence: float | None,
        actor: str = "system",
        rule_version: str = "entity_resolution.v1",
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO entity_resolution_commits (
                action, actor, before_entity_ids, after_entity_ids, evidence,
                reversible_patch, confidence, rule_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                actor,
                _json(before_entity_ids),
                _json(after_entity_ids),
                _json(evidence),
                _json(reversible_patch),
                confidence,
                rule_version,
                datetime.now(UTC).isoformat(),
            ),
        )
        return int(cursor.lastrowid)

    async def commit_entity_merge(
        self,
        winner_entity_id: int,
        loser_entity_id: int,
        *,
        reason: str,
        confidence: float,
    ) -> int:
        if winner_entity_id == loser_entity_id:
            raise ValueError("cannot merge entity into itself")
        loser_rows = await self.conn.execute_fetchall("SELECT * FROM entities WHERE id = ?", (loser_entity_id,))
        alias_rows = await self.conn.execute_fetchall("SELECT * FROM entity_aliases WHERE entity_id = ?", (loser_entity_id,))
        ref_rows = await self.conn.execute_fetchall(
            "SELECT * FROM knowledge_entity_refs WHERE entity_id = ?",
            (loser_entity_id,),
        )
        mention_rows = await self.conn.execute_fetchall(
            "SELECT id FROM entity_mentions WHERE entity_id = ?",
            (loser_entity_id,),
        )
        patch = {
            "loser": [dict(row) for row in loser_rows],
            "aliases": [dict(row) for row in alias_rows],
            "refs": [dict(row) for row in ref_rows],
            "mention_ids": [int(row["id"]) for row in mention_rows],
        }
        commit_id = await self._insert_resolution_commit(
            action="merge",
            before_entity_ids=[winner_entity_id, loser_entity_id],
            after_entity_ids=[winner_entity_id],
            evidence={"reason": reason},
            reversible_patch=patch,
            confidence=confidence,
        )
        await self.conn.execute(
            "UPDATE entities SET lifecycle_status = 'merged', merged_into_entity_id = ?, updated_at = ? WHERE id = ?",
            (winner_entity_id, datetime.now(UTC).isoformat(), loser_entity_id),
        )
        await self.conn.execute("UPDATE entity_mentions SET entity_id = ? WHERE entity_id = ?", (winner_entity_id, loser_entity_id))
        for alias in alias_rows:
            await self._insert_alias(
                winner_entity_id,
                str(alias["alias_text"]),
                alias_type=str(alias["alias_type"]),
                confidence=float(alias["confidence"]),
                scope=alias["scope"],
            )
        for ref in ref_rows:
            await self.conn.execute(
                _SQL_INSERT_KNOWLEDGE_ENTITY_REF,
                (int(ref["knowledge_object_id"]), winner_entity_id, str(ref["name"]), datetime.now(UTC).isoformat()),
            )
        await self.add_identity_edge(
            winner_entity_id,
            loser_entity_id,
            relation="same_as",
            confidence=confidence,
            evidence={"reason": reason},
            status="active",
            commit=False,
        )
        await self.conn.execute(
            "UPDATE entity_identity_edges SET commit_id = ? WHERE relation = 'same_as' AND commit_id IS NULL",
            (commit_id,),
        )
        await self.conn.commit()
        return commit_id

    async def commit_entity_split(
        self,
        entity_id: int,
        *,
        new_entity_name: str,
        mention_ids: list[int],
        reason: str,
        confidence: float,
    ) -> int:
        new_entity = ResolvedEntity(name=new_entity_name, entity_type="other", confidence=confidence, mentions=(new_entity_name,))
        new_entity_id = await self._get_or_create_entity(new_entity)
        rows = await self.conn.execute_fetchall(
            f"SELECT * FROM entity_mentions WHERE id IN ({','.join('?' for _ in mention_ids)})" if mention_ids else "SELECT * FROM entity_mentions WHERE 0",
            tuple(mention_ids),
        )
        patch = {"moved_mentions": [dict(row) for row in rows], "new_entity_id": new_entity_id}
        commit_id = await self._insert_resolution_commit(
            action="split",
            before_entity_ids=[entity_id],
            after_entity_ids=[entity_id, new_entity_id],
            evidence={"reason": reason, "mention_ids": mention_ids},
            reversible_patch=patch,
            confidence=confidence,
        )
        if mention_ids:
            placeholders = ",".join("?" for _ in mention_ids)
            await self.conn.execute(
                f"UPDATE entity_mentions SET entity_id = ?, resolution_status = 'resolved' WHERE id IN ({placeholders})",
                (new_entity_id, *mention_ids),
            )
        await self.add_identity_edge(
            entity_id,
            new_entity_id,
            relation="not_same_as",
            confidence=confidence,
            evidence={"reason": reason},
            status="active",
            commit=False,
        )
        await self.conn.execute(
            "UPDATE entity_identity_edges SET commit_id = ? WHERE relation = 'not_same_as' AND commit_id IS NULL",
            (commit_id,),
        )
        await self.conn.commit()
        return commit_id

    async def update_embedding(self, object_id: int, embedding: Embedding) -> None:
        embedding_bytes = serialize_embedding(embedding)
        await self.conn.execute(_SQL_UPDATE_KNOWLEDGE_OBJECT_EMBEDDING, (embedding_bytes, object_id))
        try:
            await self.conn.execute(_SQL_DELETE_KNOWLEDGE_OBJECT_VEC, (object_id,))
            await self.conn.execute(_SQL_INSERT_KNOWLEDGE_OBJECT_VEC, (object_id, embedding_bytes))
        except Exception:
            # Vec extension may be unavailable in lightweight tests/tools. Keep the base row updated.
            pass

    async def list_all_with_embeddings(self) -> list[KnowledgeObject]:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT * FROM knowledge_objects
            WHERE embedding IS NOT NULL AND status NOT IN ('archived', 'rejected', 'superseded')
            ORDER BY updated_at DESC
            """
        )
        return [_object_from_row(row) for row in rows]

    async def list_missing_embeddings(self, limit: int = 100) -> list[KnowledgeObject]:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT * FROM knowledge_objects
            WHERE embedding IS NULL AND status NOT IN ('archived', 'rejected', 'superseded')
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [_object_from_row(row) for row in rows]

    async def count_missing_embeddings(self) -> int:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT COUNT(*) FROM knowledge_objects
            WHERE embedding IS NULL AND status NOT IN ('archived', 'rejected', 'superseded')
            """
        )
        return int(rows[0][0]) if rows else 0

    async def count_by_type(self) -> dict[str, int]:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT object_type, COUNT(*) AS count
            FROM knowledge_objects
            WHERE status NOT IN ('archived', 'rejected', 'superseded')
            GROUP BY object_type
            """
        )
        return {str(row["object_type"]): int(row["count"]) for row in rows}

    async def update(self, object_id: int, payload: KnowledgeObjectUpdate) -> KnowledgeObject:
        existing = await self.get(object_id)
        if existing is None:
            raise KeyError(f"Knowledge object {object_id} not found")

        data = payload.model_dump(exclude_unset=True)
        if not data:
            return existing

        assignments: list[str] = []
        params: list[object] = []
        for key, value in data.items():
            if key in {"object_type"}:
                continue
            assignments.append(f"{key} = ?")
            if key == "status":
                params.append(value.value)
            elif key in {"source_ids", "metadata"}:
                params.append(_json(value))
            else:
                params.append(value)

        now = datetime.now(UTC).isoformat()
        assignments.append("updated_at = ?")
        params.append(now)
        if payload.status in {KnowledgeObjectStatus.APPROVED, KnowledgeObjectStatus.REJECTED}:
            assignments.append("reviewed_at = ?")
            params.append(now)

        params.append(object_id)
        await self.conn.execute(
            f"UPDATE knowledge_objects SET {', '.join(assignments)} WHERE id = ?",
            tuple(params),
        )
        await self.conn.commit()
        updated = await self.get(object_id)
        if updated is None:
            raise RuntimeError("knowledge object disappeared after update")
        return updated
