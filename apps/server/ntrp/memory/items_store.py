import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import aiosqlite
import numpy as np

from ntrp.database import serialize_embedding

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


class MemoryItemsRepository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def embedding_dim(self) -> int | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_EMBEDDING_DIM)
        if not rows:
            return None
        return int(rows[0]["value"])

    async def insert_item(self, item: MemoryItemInsert) -> str:
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
        await self.conn.commit()
        return item_id
