import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import aiosqlite

from ntrp.memory.models import MemoryAccessEvent

_SQL_INSERT_ACCESS_EVENT = """
    INSERT INTO memory_access_events (
        created_at, source, query,
        retrieved_fact_ids, retrieved_observation_ids,
        injected_fact_ids, injected_observation_ids,
        omitted_fact_ids, omitted_observation_ids,
        bundled_fact_ids, formatted_chars, policy_version, details
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_LIST_ACCESS_EVENTS = """
    SELECT * FROM memory_access_events
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


def _json_list(values: list[int] | None) -> str:
    return json.dumps(values or [], sort_keys=True)


def _row_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    for key in (
        "retrieved_fact_ids",
        "retrieved_observation_ids",
        "injected_fact_ids",
        "injected_observation_ids",
        "omitted_fact_ids",
        "omitted_observation_ids",
        "bundled_fact_ids",
    ):
        d[key] = json.loads(d[key]) if d.get(key) else []
    d["details"] = json.loads(d["details"]) if d.get("details") else {}
    return d


class MemoryAccessEventRepository:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def create(
        self,
        *,
        source: str,
        query: str | None = None,
        retrieved_fact_ids: list[int] | None = None,
        retrieved_observation_ids: list[int] | None = None,
        injected_fact_ids: list[int] | None = None,
        injected_observation_ids: list[int] | None = None,
        omitted_fact_ids: list[int] | None = None,
        omitted_observation_ids: list[int] | None = None,
        bundled_fact_ids: list[int] | None = None,
        formatted_chars: int = 0,
        policy_version: str,
        details: dict[str, Any] | None = None,
    ) -> MemoryAccessEvent:
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_INSERT_ACCESS_EVENT,
            (
                now.isoformat(),
                source,
                query,
                _json_list(retrieved_fact_ids),
                _json_list(retrieved_observation_ids),
                _json_list(injected_fact_ids),
                _json_list(injected_observation_ids),
                _json_list(omitted_fact_ids),
                _json_list(omitted_observation_ids),
                _json_list(bundled_fact_ids),
                max(0, formatted_chars),
                policy_version,
                json.dumps(details or {}, default=_json_default, sort_keys=True),
            ),
        )
        return MemoryAccessEvent(
            id=cursor.lastrowid,
            created_at=now,
            source=source,
            query=query,
            retrieved_fact_ids=retrieved_fact_ids or [],
            retrieved_observation_ids=retrieved_observation_ids or [],
            injected_fact_ids=injected_fact_ids or [],
            injected_observation_ids=injected_observation_ids or [],
            omitted_fact_ids=omitted_fact_ids or [],
            omitted_observation_ids=omitted_observation_ids or [],
            bundled_fact_ids=bundled_fact_ids or [],
            formatted_chars=max(0, formatted_chars),
            policy_version=policy_version,
            details=details or {},
        )

    async def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        source: str | None = None,
    ) -> list[MemoryAccessEvent]:
        where = []
        params: list[object] = []
        if source is not None:
            where.append("source = ?")
            params.append(source)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = await self.read_conn.execute_fetchall(
            _SQL_LIST_ACCESS_EVENTS.format(where=where_sql),
            (*params, limit, offset),
        )
        return [MemoryAccessEvent.model_validate(_row_dict(row)) for row in rows]
