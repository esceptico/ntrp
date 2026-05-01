import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import aiosqlite

from ntrp.memory.models import MemoryEvent

_SQL_INSERT_EVENT = """
    INSERT INTO memory_events (
        created_at, actor, action, target_type, target_id,
        source_type, source_ref, reason, policy_version, details
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_LIST_EVENTS = """
    SELECT * FROM memory_events
    {where}
    ORDER BY created_at DESC, id DESC
    LIMIT ? OFFSET ?
"""


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _row_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    d["details"] = json.loads(d["details"]) if d.get("details") else {}
    return d


class MemoryEventRepository:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def create(
        self,
        *,
        actor: str,
        action: str,
        target_type: str,
        target_id: int | None = None,
        source_type: str | None = None,
        source_ref: str | None = None,
        reason: str | None = None,
        policy_version: str,
        details: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_INSERT_EVENT,
            (
                now.isoformat(),
                actor,
                action,
                target_type,
                target_id,
                source_type,
                source_ref,
                reason,
                policy_version,
                json.dumps(details or {}, default=_json_default, sort_keys=True),
            ),
        )
        return MemoryEvent(
            id=cursor.lastrowid,
            created_at=now,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            source_type=source_type,
            source_ref=source_ref,
            reason=reason,
            policy_version=policy_version,
            details=details or {},
        )

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        target_type: str | None = None,
        target_id: int | None = None,
        action: str | None = None,
    ) -> list[MemoryEvent]:
        where = []
        params: list[object] = []
        if target_type is not None:
            where.append("target_type = ?")
            params.append(target_type)
        if target_id is not None:
            where.append("target_id = ?")
            params.append(target_id)
        if action is not None:
            where.append("action = ?")
            params.append(action)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = await self.read_conn.execute_fetchall(
            _SQL_LIST_EVENTS.format(where=where_sql),
            (*params, limit, offset),
        )
        return [MemoryEvent.model_validate(_row_dict(row)) for row in rows]
