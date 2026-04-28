import json
from datetime import UTC, datetime

import aiosqlite

from ntrp.events.internal import RunCompleted
from ntrp.outbox.events import OUTBOX_RUN_COMPLETED, run_completed_payload
from ntrp.outbox.models import OutboxEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    aggregate_type TEXT,
    aggregate_id TEXT,
    payload TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    locked_at TEXT,
    locked_by TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outbox_events_ready
ON outbox_events(status, available_at, id);

CREATE INDEX IF NOT EXISTS idx_outbox_events_aggregate
ON outbox_events(aggregate_type, aggregate_id);
"""

_SQL_ENQUEUE = """
INSERT OR IGNORE INTO outbox_events (
    event_type,
    aggregate_type,
    aggregate_id,
    payload,
    idempotency_key,
    status,
    attempts,
    available_at,
    created_at,
    updated_at
)
VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
"""

_SQL_CLAIM_CANDIDATES = """
SELECT *
FROM outbox_events
WHERE status = 'pending'
  AND available_at <= ?
ORDER BY id
LIMIT ?
"""

_SQL_CLAIM = """
UPDATE outbox_events
SET status = 'running',
    attempts = attempts + 1,
    locked_at = ?,
    locked_by = ?,
    updated_at = ?
WHERE id = ?
  AND status = 'pending'
"""

_SQL_COMPLETE = """
UPDATE outbox_events
SET status = 'completed',
    locked_at = NULL,
    locked_by = NULL,
    updated_at = ?
WHERE id = ?
"""

_SQL_FAIL = """
UPDATE outbox_events
SET status = ?,
    available_at = ?,
    locked_at = NULL,
    locked_by = NULL,
    last_error = ?,
    updated_at = ?
WHERE id = ?
"""

_SQL_RELEASE_STALE = """
UPDATE outbox_events
SET status = 'pending',
    locked_at = NULL,
    locked_by = NULL,
    updated_at = ?
WHERE status = 'running'
  AND locked_at < ?
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _format_dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _parse_dt(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw) if raw else None


def _row_data(row: aiosqlite.Row) -> dict:
    return dict(row)


def _event_from_data(data: dict) -> OutboxEvent:
    return OutboxEvent(
        id=int(data["id"]),
        event_type=data["event_type"],
        aggregate_type=data["aggregate_type"],
        aggregate_id=data["aggregate_id"],
        payload=json.loads(data["payload"]),
        idempotency_key=data["idempotency_key"],
        status=data["status"],
        attempts=int(data["attempts"]),
        available_at=_parse_dt(data["available_at"]),
        locked_at=_parse_dt(data["locked_at"]),
        locked_by=data["locked_by"],
        last_error=data["last_error"],
        created_at=_parse_dt(data["created_at"]),
        updated_at=_parse_dt(data["updated_at"]),
    )


class OutboxStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def init_schema(self) -> None:
        await self.conn.executescript(_SCHEMA)
        await self.conn.commit()

    async def enqueue(
        self,
        *,
        event_type: str,
        payload: dict,
        idempotency_key: str,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        available_at: datetime | None = None,
    ) -> bool:
        now = _now()
        available = available_at or now
        cursor = await self.conn.execute(
            _SQL_ENQUEUE,
            (
                event_type,
                aggregate_type,
                aggregate_id,
                json.dumps(payload),
                idempotency_key,
                _format_dt(available),
                _format_dt(now),
                _format_dt(now),
            ),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def enqueue_run_completed(self, event: RunCompleted) -> bool:
        return await self.enqueue(
            event_type=OUTBOX_RUN_COMPLETED,
            aggregate_type="run",
            aggregate_id=event.run_id,
            payload=run_completed_payload(event),
            idempotency_key=f"{OUTBOX_RUN_COMPLETED}:{event.run_id}",
        )

    async def claim_batch(self, *, worker_id: str, limit: int, now: datetime | None = None) -> list[OutboxEvent]:
        claimed_at = now or _now()
        rows = await self.conn.execute_fetchall(
            _SQL_CLAIM_CANDIDATES,
            (_format_dt(claimed_at), limit),
        )

        events: list[OutboxEvent] = []
        for row in rows:
            data = _row_data(row)
            cursor = await self.conn.execute(
                _SQL_CLAIM,
                (
                    _format_dt(claimed_at),
                    worker_id,
                    _format_dt(claimed_at),
                    data["id"],
                ),
            )
            if cursor.rowcount <= 0:
                continue
            data["status"] = "running"
            data["attempts"] = int(data["attempts"]) + 1
            data["locked_at"] = _format_dt(claimed_at)
            data["locked_by"] = worker_id
            data["updated_at"] = _format_dt(claimed_at)
            events.append(_event_from_data(data))

        await self.conn.commit()
        return events

    async def mark_completed(self, event_id: int) -> None:
        now = _now()
        await self.conn.execute(_SQL_COMPLETE, (_format_dt(now), event_id))
        await self.conn.commit()

    async def mark_failed(
        self,
        event_id: int,
        *,
        error: str,
        retry_at: datetime | None,
        dead: bool = False,
    ) -> None:
        now = _now()
        status = "dead" if dead else "pending"
        available_at = retry_at or now
        await self.conn.execute(
            _SQL_FAIL,
            (
                status,
                _format_dt(available_at),
                error[:2000],
                _format_dt(now),
                event_id,
            ),
        )
        await self.conn.commit()

    async def release_stale_running(self, locked_before: datetime) -> int:
        now = _now()
        cursor = await self.conn.execute(
            _SQL_RELEASE_STALE,
            (_format_dt(now), _format_dt(locked_before)),
        )
        await self.conn.commit()
        return cursor.rowcount
