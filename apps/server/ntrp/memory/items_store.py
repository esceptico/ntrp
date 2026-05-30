import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite
import numpy as np

from ntrp.database import deserialize_embedding, serialize_embedding

_TITLE_MAX_CHARS = 80
_MD_STRIP = re.compile(r"[#*_`>\[\]]+")


def derive_title(content: str) -> str:
    """First markdown heading or sentence, stripped of markdown, capped for display."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            break
    else:
        return ""
    if stripped.startswith("#"):
        stripped = stripped.lstrip("#").strip()
    stripped = _MD_STRIP.sub("", stripped).strip()
    sentence = re.split(r"(?<=[.!?])\s", stripped, maxsplit=1)[0]
    title = sentence.strip()
    if len(title) > _TITLE_MAX_CHARS:
        title = title[: _TITLE_MAX_CHARS - 1].rstrip() + "…"
    return title

_SQL_INSERT_ITEM = """
INSERT INTO memory_items (
    id, kind, content, title, provenance, source_refs, confidence, status,
    valid_from, invalid_at, scope, tags, artifact_ref, usage, feedback,
    created_at, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_INSERT_ITEM_VEC = "INSERT INTO memory_items_vec (item_id, embedding) VALUES (?, ?)"

_SQL_GET_EMBEDDING_DIM = "SELECT value FROM meta WHERE key = 'embedding_dim'"

_SQL_INSERT_PARENT_EDGE = """
INSERT OR IGNORE INTO memory_item_parents (child_id, parent_id, role, "order")
VALUES (?, ?, ?, ?)
"""

_SQL_LIST_PARENT_EDGES = """
SELECT child_id, parent_id, role, "order", created_at
FROM memory_item_parents
WHERE child_id = ?
ORDER BY role, "order", parent_id
"""

_SQL_LIST_CHILD_EDGES = """
SELECT child_id, parent_id, role, "order", created_at
FROM memory_item_parents
WHERE parent_id = ?
ORDER BY role, "order", child_id
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _format_dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


@dataclass
class MemoryItemInsert:
    content: str
    source_refs: list[dict]
    confidence: float
    title: str | None = None
    scope: str = "user"
    kind: str = "episode"
    provenance: str = "inferred"
    status: str = "active"
    tags: list[str] = field(default_factory=list)
    artifact_ref: str | None = None
    usage: dict = field(default_factory=lambda: {"activated": 0, "helped": 0, "hurt": 0, "ignored": 0})
    feedback: dict = field(default_factory=lambda: {"thumbs_up": 0, "thumbs_down": 0, "corrections": 0})
    embedding: np.ndarray | None = None
    valid_from: datetime | None = None
    invalid_at: datetime | None = None


@dataclass(slots=True)
class MemoryItem:
    id: str
    kind: str
    content: str
    title: str | None
    provenance: str
    source_refs: list[dict[str, Any]]
    confidence: float
    status: str
    valid_from: datetime
    invalid_at: datetime | None
    scope: str
    tags: list[str]
    artifact_ref: str | None
    usage: dict[str, Any]
    feedback: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    embedding: np.ndarray | None


@dataclass(slots=True)
class MemoryItemParent:
    child_id: str
    parent_id: str
    role: str
    order: int | None
    created_at: datetime


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = datetime.fromisoformat(str(raw))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _loads_json(raw: str | None, fallback):
    if not raw:
        return fallback
    return json.loads(raw)


def _row_to_item(row: aiosqlite.Row) -> MemoryItem:
    return MemoryItem(
        id=str(row["id"]),
        kind=str(row["kind"]),
        content=str(row["content"]),
        title=row["title"],
        provenance=str(row["provenance"]),
        source_refs=_loads_json(row["source_refs"], []),
        confidence=float(row["confidence"]),
        status=str(row["status"]),
        valid_from=_parse_dt(row["valid_from"]),
        invalid_at=_parse_dt(row["invalid_at"]),
        scope=str(row["scope"]),
        tags=_loads_json(row["tags"], []),
        artifact_ref=row["artifact_ref"],
        usage=_loads_json(row["usage"], {}),
        feedback=_loads_json(row["feedback"], {}),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        embedding=deserialize_embedding(row["embedding"]),
    )


def _row_to_parent(row: aiosqlite.Row) -> MemoryItemParent:
    return MemoryItemParent(
        child_id=str(row["child_id"]),
        parent_id=str(row["parent_id"]),
        role=str(row["role"]),
        order=row["order"],
        created_at=_parse_dt(row["created_at"]),
    )


def _apply_validity_filter(clauses: list[str], params: list[Any], *, alias: str, validity: str | None, at: datetime | None) -> None:
    if not validity or validity == "all":
        return
    timestamp = _format_dt(at or _now())
    prefix = f"{alias}." if alias else ""
    if validity == "current":
        clauses.append(f"datetime({prefix}valid_from) <= datetime(?)")
        params.append(timestamp)
        clauses.append(f"({prefix}invalid_at IS NULL OR datetime({prefix}invalid_at) > datetime(?))")
        params.append(timestamp)
        return
    if validity == "future":
        clauses.append(f"datetime({prefix}valid_from) > datetime(?)")
        params.append(timestamp)
        return
    if validity in {"expired", "invalid"}:
        clauses.append(f"{prefix}invalid_at IS NOT NULL AND datetime({prefix}invalid_at) <= datetime(?)")
        params.append(timestamp)
        return
    raise ValueError(f"invalid validity filter: {validity}")


class MemoryItemsRepository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def embedding_dim(self) -> int | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_EMBEDDING_DIM)
        if not rows:
            return None
        return int(rows[0]["value"])

    async def list_recent_items(
        self,
        *,
        kind: str,
        window_days: int,
        limit: int,
        scope: str,
        now: datetime | None = None,
    ) -> list[MemoryItem]:
        window_start = (now or _now()) - timedelta(days=window_days)
        rows = await self.conn.execute_fetchall(
            """
            SELECT m.*, v.embedding
            FROM memory_items m
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE m.kind = ?
              AND m.scope = ?
              AND m.status = 'active'
              AND m.valid_from >= ?
            ORDER BY m.valid_from DESC, m.id
            LIMIT ?
            """,
            (kind, scope, _format_dt(window_start), limit),
        )
        return [_row_to_item(row) for row in rows]

    async def list_recent_items_all_scopes(
        self,
        *,
        kind: str,
        window_days: int,
        limit: int,
        now: datetime | None = None,
    ) -> list[MemoryItem]:
        window_start = (now or _now()) - timedelta(days=window_days)
        rows = await self.conn.execute_fetchall(
            """
            SELECT m.*, v.embedding
            FROM memory_items m
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE m.kind = ?
              AND m.status = 'active'
              AND m.valid_from >= ?
            ORDER BY m.valid_from DESC, m.id
            LIMIT ?
            """,
            (kind, _format_dt(window_start), limit),
        )
        return [_row_to_item(row) for row in rows]

    async def insert_item(self, item: MemoryItemInsert, *, commit: bool = True) -> str:
        item_id = uuid.uuid4().hex
        now = _now()
        valid_from = item.valid_from or now
        embedding = serialize_embedding(item.embedding)
        title = item.title or derive_title(item.content) or None
        await self.conn.execute(
            _SQL_INSERT_ITEM,
            (
                item_id,
                item.kind,
                item.content,
                title,
                item.provenance,
                json.dumps(item.source_refs, sort_keys=True),
                item.confidence,
                item.status,
                _format_dt(valid_from),
                _format_dt(item.invalid_at) if item.invalid_at else None,
                item.scope,
                json.dumps(item.tags, sort_keys=True),
                item.artifact_ref,
                json.dumps(item.usage, sort_keys=True),
                json.dumps(item.feedback, sort_keys=True),
                _format_dt(now),
                _format_dt(now),
            ),
        )
        if embedding is not None:
            await self.conn.execute(_SQL_INSERT_ITEM_VEC, (item_id, embedding))
        if commit:
            await self.conn.commit()
        return item_id

    async def update_status(
        self,
        item_id: str,
        status: str,
        *,
        invalid_at: datetime | None = None,
        commit: bool = True,
    ) -> None:
        now = _now()
        await self.conn.execute(
            "UPDATE memory_items SET status = ?, invalid_at = ?, updated_at = ? WHERE id = ?",
            (status, _format_dt(invalid_at) if invalid_at else None, _format_dt(now), item_id),
        )
        if commit:
            await self.conn.commit()

    async def update_item(
        self,
        item_id: str,
        *,
        content: str,
        title: str | None,
        confidence: float,
        tags: list[str],
        scope: str,
        status: str,
        invalid_at: datetime | None,
        embedding: np.ndarray | None = None,
        commit: bool = True,
    ) -> None:
        """Edit an item's mutable fields. The FTS index syncs via trigger; the
        vector row is replaced here when a fresh embedding is supplied."""
        await self.conn.execute(
            """
            UPDATE memory_items
            SET content = ?, title = ?, confidence = ?, tags = ?, scope = ?,
                status = ?, invalid_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                content,
                title,
                confidence,
                json.dumps(tags, sort_keys=True),
                scope,
                status,
                _format_dt(invalid_at) if invalid_at else None,
                _format_dt(_now()),
                item_id,
            ),
        )
        if embedding is not None:
            serialized = serialize_embedding(embedding)
            if serialized is not None:
                await self.conn.execute("DELETE FROM memory_items_vec WHERE item_id = ?", (item_id,))
                await self.conn.execute(_SQL_INSERT_ITEM_VEC, (item_id, serialized))
        if commit:
            await self.conn.commit()

    async def delete_item(self, item_id: str, *, commit: bool = True) -> None:
        """Hard-delete an item. Edges cascade via ON DELETE CASCADE."""
        await self.conn.execute("DELETE FROM memory_items WHERE id = ?", (item_id,))
        if commit:
            await self.conn.commit()

    async def insert_parent_edge(
        self,
        child_id: str,
        parent_id: str,
        role: str,
        order: int | None = None,
        *,
        commit: bool = True,
    ) -> None:
        if child_id == parent_id:
            raise ValueError("memory item parent graph must be acyclic: self-edge rejected")
        if await self._edge_would_create_cycle(child_id, parent_id):
            raise ValueError("memory item parent graph must be acyclic")
        await self.conn.execute(_SQL_INSERT_PARENT_EDGE, (child_id, parent_id, role, order))
        if commit:
            await self.conn.commit()

    async def _edge_would_create_cycle(self, child_id: str, parent_id: str) -> bool:
        rows = await self.conn.execute_fetchall(
            """
            WITH RECURSIVE ancestors(id) AS (
                SELECT parent_id
                FROM memory_item_parents
                WHERE child_id = ?
              UNION
                SELECT p.parent_id
                FROM memory_item_parents p
                JOIN ancestors a ON p.child_id = a.id
            )
            SELECT 1
            FROM ancestors
            WHERE id = ?
            LIMIT 1
            """,
            (parent_id, child_id),
        )
        return bool(rows)

    async def list_all_edges(self) -> list[MemoryItemParent]:
        rows = await self.conn.execute_fetchall(
            'SELECT child_id, parent_id, role, "order", created_at FROM memory_item_parents ORDER BY role, "order", child_id'
        )
        return [_row_to_parent(row) for row in rows]

    async def list_graph_items(
        self,
        *,
        include_unlinked: bool,
        scope: str | None = None,
    ) -> list[MemoryItem]:
        clauses = ["m.status != 'archived'"]
        params: list[Any] = []
        if scope:
            clauses.append("m.scope = ?")
            params.append(scope)
        if not include_unlinked:
            clauses.append(
                "(m.kind != 'episode' OR m.id IN "
                "(SELECT child_id FROM memory_item_parents UNION SELECT parent_id FROM memory_item_parents))"
            )
        rows = await self.conn.execute_fetchall(
            f"""
            SELECT m.*, v.embedding
            FROM memory_items m
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE {' AND '.join(clauses)}
            ORDER BY datetime(m.updated_at) DESC, m.id
            """,
            params,
        )
        return [_row_to_item(row) for row in rows]

    async def list_parent_edges(self, child_id: str) -> list[MemoryItemParent]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_PARENT_EDGES, (child_id,))
        return [_row_to_parent(row) for row in rows]

    async def list_child_edges(self, parent_id: str) -> list[MemoryItemParent]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_CHILD_EDGES, (parent_id,))
        return [_row_to_parent(row) for row in rows]

    async def ensure_directory(
        self,
        slug: str,
        name: str,
        description: str,
        *,
        scope: str = "user",
        commit: bool = True,
    ) -> str:
        """Idempotently materialize a lens-declared directory node.

        Keyed by a ``lens:<slug>`` tag so re-running a lens reuses (and refreshes)
        the same node rather than spawning duplicates.
        """
        tag = f"lens:{slug}"
        rows = await self.conn.execute_fetchall(
            "SELECT id FROM memory_items WHERE kind = 'directory' AND tags LIKE ? LIMIT 1",
            (f'%"{tag}"%',),
        )
        if rows:
            directory_id = rows[0]["id"]
            await self.conn.execute(
                "UPDATE memory_items SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                (name, description, _format_dt(_now()), directory_id),
            )
            if commit:
                await self.conn.commit()
            return directory_id
        return await self.insert_item(
            MemoryItemInsert(
                content=description,
                source_refs=[],
                confidence=1.0,
                title=name,
                scope=scope,
                kind="directory",
                provenance="user_authored",
                tags=[tag],
            ),
            commit=commit,
        )

    async def list_directories(self, *, scope: str | None = None) -> list[MemoryItem]:
        return await self.list_items(kinds=["directory"], statuses=["active"], scope=scope, limit=500)

    async def find_entity_by_title(self, title: str, *, scope: str = "user") -> MemoryItem | None:
        rows = await self.conn.execute_fetchall(
            """
            SELECT m.*, v.embedding
            FROM memory_items m
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE m.kind = 'entity' AND m.status = 'active' AND m.scope = ?
              AND lower(m.title) = lower(?)
            LIMIT 1
            """,
            (scope, title),
        )
        return _row_to_item(rows[0]) if rows else None

    async def list_directory_members(self, directory_id: str) -> list[MemoryItem]:
        rows = await self.conn.execute_fetchall(
            """
            SELECT m.*, v.embedding
            FROM memory_item_parents e
            JOIN memory_items m ON m.id = e.child_id
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE e.parent_id = ? AND e.role = 'member_of' AND m.status != 'archived'
            ORDER BY m.title, m.id
            """,
            (directory_id,),
        )
        return [_row_to_item(row) for row in rows]

    async def get_item(self, item_id: str) -> MemoryItem | None:
        rows = await self.conn.execute_fetchall(
            """
            SELECT m.*, v.embedding
            FROM memory_items m
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE m.id = ?
            """,
            (item_id,),
        )
        return _row_to_item(rows[0]) if rows else None

    async def list_items(
        self,
        *,
        kinds: list[str] | None = None,
        statuses: list[str] | None = None,
        scope: str | None = None,
        validity: str | None = None,
        validity_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryItem]:
        clauses: list[str] = []
        params: list[Any] = []
        if kinds:
            clauses.append(f"m.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        if statuses:
            clauses.append(f"m.status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        if scope:
            clauses.append("m.scope = ?")
            params.append(scope)
        _apply_validity_filter(clauses, params, alias="m", validity=validity, at=validity_at)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = await self.conn.execute_fetchall(
            f"""
            SELECT m.*, v.embedding
            FROM memory_items m
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            {where}
            ORDER BY datetime(m.updated_at) DESC, m.id
            LIMIT ? OFFSET ?
            """,
            params,
        )
        return [_row_to_item(row) for row in rows]

    async def count_items(
        self,
        *,
        kinds: list[str] | None = None,
        statuses: list[str] | None = None,
        scope: str | None = None,
        validity: str | None = None,
        validity_at: datetime | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if kinds:
            clauses.append(f"kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        if statuses:
            clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        _apply_validity_filter(clauses, params, alias="", validity=validity, at=validity_at)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self.conn.execute_fetchall(
            f"SELECT COUNT(*) FROM memory_items {where}",
            params,
        )
        return int(rows[0][0]) if rows else 0

    async def search_items_fts(
        self,
        query: str,
        *,
        kinds: list[str] | None = None,
        statuses: list[str] | None = None,
        scope: str | None = None,
        validity: str | None = None,
        validity_at: datetime | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        where_clauses: list[str] = ["memory_items_fts MATCH ?"]
        params: list[Any] = [query]
        if kinds:
            where_clauses.append(f"m.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        if statuses:
            where_clauses.append(f"m.status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        if scope:
            where_clauses.append("m.scope = ?")
            params.append(scope)
        _apply_validity_filter(where_clauses, params, alias="m", validity=validity, at=validity_at)
        params.append(limit)
        rows = await self.conn.execute_fetchall(
            f"""
            SELECT m.*, v.embedding, bm25(memory_items_fts) AS rank
            FROM memory_items_fts
            JOIN memory_items m ON m.id = memory_items_fts.item_id
            LEFT JOIN memory_items_vec v ON v.item_id = m.id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY rank
            LIMIT ?
            """,
            params,
        )
        return [_row_to_item(row) for row in rows]
