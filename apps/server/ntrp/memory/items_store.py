import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite
import numpy as np

from ntrp.database import deserialize_embedding, serialize_embedding

_SQL_INSERT_ITEM = """
INSERT INTO memory_items (
    id, kind, content, provenance, source_refs, confidence, status,
    valid_from, invalid_at, scope, tags, artifact_ref, usage, feedback,
    created_at, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


class MemoryItemsRepository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def embedding_dim(self) -> int | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_EMBEDDING_DIM)
        if not rows:
            return None
        return int(rows[0]["value"])

    async def list_recent_items(self, *, kind: str, window_days: int, limit: int, scope: str) -> list[MemoryItem]:
        window_start = _now() - timedelta(days=window_days)
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

    async def insert_item(self, item: MemoryItemInsert, *, commit: bool = True) -> str:
        item_id = uuid.uuid4().hex
        now = _now()
        valid_from = item.valid_from or now
        embedding = serialize_embedding(item.embedding)
        await self.conn.execute(
            _SQL_INSERT_ITEM,
            (
                item_id,
                item.kind,
                item.content,
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

    async def insert_parent_edge(
        self,
        child_id: str,
        parent_id: str,
        role: str,
        order: int | None = None,
        *,
        commit: bool = True,
    ) -> None:
        await self.conn.execute(_SQL_INSERT_PARENT_EDGE, (child_id, parent_id, role, order))
        if commit:
            await self.conn.commit()

    async def list_parent_edges(self, child_id: str) -> list[MemoryItemParent]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_PARENT_EDGES, (child_id,))
        return [_row_to_parent(row) for row in rows]
