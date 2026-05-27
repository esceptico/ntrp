import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiosqlite
import numpy as np

_TURN_SEPARATOR = "\n\n---\n\n"

_SQL_FIND_OPEN = """
SELECT *
FROM episode_buffers
WHERE scope = ?
  AND source_kind = ?
  AND closed_at IS NULL
LIMIT 1
"""

_SQL_GET_BUFFER = "SELECT * FROM episode_buffers WHERE id = ?"

_SQL_CREATE_BUFFER = """
INSERT INTO episode_buffers (
    id, scope, source_kind, started_at, last_activity_at, turn_count,
    tokens, content_so_far, source_refs_so_far, running_centroid_vec, closed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
"""

_SQL_UPDATE_BUFFER = """
UPDATE episode_buffers
SET last_activity_at = ?,
    turn_count = ?,
    tokens = ?,
    content_so_far = ?,
    source_refs_so_far = ?,
    running_centroid_vec = ?
WHERE id = ?
"""

_SQL_CLOSE_BUFFER = "UPDATE episode_buffers SET closed_at = ? WHERE id = ? AND closed_at IS NULL"

_SQL_FIND_IDLE = """
SELECT *
FROM episode_buffers
WHERE closed_at IS NULL
  AND last_activity_at < ?
ORDER BY last_activity_at ASC
"""


@dataclass
class BufferCarry:
    content: str
    source_refs: list[dict]
    centroid: np.ndarray | None
    turn_count: int
    tokens: int


@dataclass
class TurnUpdate:
    content: str
    tokens: int
    source_ref: dict
    embedding: np.ndarray


@dataclass
class EpisodeBuffer:
    id: str
    scope: str
    source_kind: str
    started_at: datetime
    last_activity_at: datetime
    turn_count: int
    tokens: int
    content_so_far: str
    source_refs_so_far: list[dict]
    running_centroid_vec: np.ndarray | None
    closed_at: datetime | None

    @property
    def content_turns(self) -> list[str]:
        if not self.content_so_far:
            return []
        return self.content_so_far.split(_TURN_SEPARATOR)


def join_turns(turns: list[str]) -> str:
    return _TURN_SEPARATOR.join(turn for turn in turns if turn)


def _now() -> datetime:
    return datetime.now(UTC)


def _format_dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = datetime.fromisoformat(raw)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _serialize_vec(vec: np.ndarray | None) -> bytes | None:
    if vec is None:
        return None
    return vec.astype(np.float32).tobytes()


def _deserialize_vec(blob: bytes | None) -> np.ndarray | None:
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32).copy()


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


def _row_to_buffer(row: aiosqlite.Row) -> EpisodeBuffer:
    refs_raw = row["source_refs_so_far"] or "[]"
    return EpisodeBuffer(
        id=row["id"],
        scope=row["scope"],
        source_kind=row["source_kind"],
        started_at=_parse_dt(row["started_at"]),
        last_activity_at=_parse_dt(row["last_activity_at"]),
        turn_count=int(row["turn_count"]),
        tokens=int(row["tokens"]),
        content_so_far=row["content_so_far"] or "",
        source_refs_so_far=json.loads(refs_raw),
        running_centroid_vec=_deserialize_vec(row["running_centroid_vec"]),
        closed_at=_parse_dt(row["closed_at"]),
    )


def _append_turn_content(existing: str, content: str) -> str:
    if not existing:
        return content
    return f"{existing}{_TURN_SEPARATOR}{content}"


def _updated_centroid(existing: np.ndarray | None, count: int, turn_vec: np.ndarray) -> np.ndarray:
    turn_vec = _normalize(turn_vec.astype(np.float32))
    if existing is None or count <= 0:
        return turn_vec
    return _normalize((existing.astype(np.float32) * count + turn_vec) / (count + 1))


class EpisodeBufferRepository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn
        self._lock = asyncio.Lock()

    async def find_open(self, scope: str, source_kind: str) -> EpisodeBuffer | None:
        rows = await self.conn.execute_fetchall(_SQL_FIND_OPEN, (scope, source_kind))
        return _row_to_buffer(rows[0]) if rows else None

    async def create(self, scope: str, source_kind: str, *, carry: BufferCarry | None = None) -> EpisodeBuffer:
        async with self._lock:
            now = _now()
            buffer_id = uuid.uuid4().hex
            turn_count = carry.turn_count if carry else 0
            tokens = carry.tokens if carry else 0
            content = carry.content if carry else ""
            source_refs = carry.source_refs if carry else []
            centroid = carry.centroid if carry else None
            await self.conn.execute(
                _SQL_CREATE_BUFFER,
                (
                    buffer_id,
                    scope,
                    source_kind,
                    _format_dt(now),
                    _format_dt(now),
                    turn_count,
                    tokens,
                    content,
                    json.dumps(source_refs, sort_keys=True),
                    _serialize_vec(centroid),
                ),
            )
            await self.conn.commit()
        buffer = await self._get(buffer_id)
        if buffer is None:
            raise RuntimeError(f"created episode buffer disappeared: {buffer_id}")
        return buffer

    async def apply_turn(self, buffer_id: str, turn: TurnUpdate) -> EpisodeBuffer:
        async with self._lock:
            buffer = await self._get(buffer_id)
            if buffer is None:
                raise ValueError(f"episode buffer not found: {buffer_id}")
            now = _now()
            refs = [*buffer.source_refs_so_far, turn.source_ref]
            centroid = _updated_centroid(buffer.running_centroid_vec, buffer.turn_count, turn.embedding)
            await self.conn.execute(
                _SQL_UPDATE_BUFFER,
                (
                    _format_dt(now),
                    buffer.turn_count + 1,
                    buffer.tokens + max(0, turn.tokens),
                    _append_turn_content(buffer.content_so_far, turn.content),
                    json.dumps(refs, sort_keys=True),
                    _serialize_vec(centroid),
                    buffer.id,
                ),
            )
            await self.conn.commit()
        updated = await self._get(buffer_id)
        if updated is None:
            raise RuntimeError(f"updated episode buffer disappeared: {buffer_id}")
        return updated

    async def close(self, buffer_id: str) -> None:
        async with self._lock:
            await self.conn.execute(_SQL_CLOSE_BUFFER, (_format_dt(_now()), buffer_id))
            await self.conn.commit()

    async def find_idle(self, threshold_minutes: float) -> list[EpisodeBuffer]:
        cutoff = _now() - timedelta(minutes=threshold_minutes)
        rows = await self.conn.execute_fetchall(_SQL_FIND_IDLE, (_format_dt(cutoff),))
        return [_row_to_buffer(row) for row in rows]

    async def _get(self, buffer_id: str) -> EpisodeBuffer | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_BUFFER, (buffer_id,))
        return _row_to_buffer(rows[0]) if rows else None
