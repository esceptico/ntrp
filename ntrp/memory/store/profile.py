import json
from datetime import UTC, datetime

import aiosqlite

from ntrp.memory.models import FactKind, ProfileEntry

_SQL_LIST_ACTIVE = """
    SELECT * FROM profile_entries
    WHERE archived_at IS NULL
    ORDER BY updated_at DESC, id DESC
    LIMIT ?
"""

_SQL_GET = "SELECT * FROM profile_entries WHERE id = ?"

_SQL_INSERT = """
    INSERT INTO profile_entries (
        kind, summary, source_fact_ids, source_observation_ids,
        created_at, updated_at, created_by, policy_version, confidence
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_UPDATE = """
    UPDATE profile_entries
    SET kind = ?, summary = ?, source_fact_ids = ?, source_observation_ids = ?,
        updated_at = ?, policy_version = ?, confidence = ?
    WHERE id = ? AND archived_at IS NULL
"""

_SQL_ARCHIVE = """
    UPDATE profile_entries
    SET archived_at = ?, updated_at = ?
    WHERE id = ? AND archived_at IS NULL
"""


def _row_dict(row: aiosqlite.Row) -> dict:
    data = dict(row)
    data["source_fact_ids"] = json.loads(data["source_fact_ids"]) if data.get("source_fact_ids") else []
    data["source_observation_ids"] = (
        json.loads(data["source_observation_ids"]) if data.get("source_observation_ids") else []
    )
    return data


class ProfileRepository:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def list_active(self, limit: int) -> list[ProfileEntry]:
        rows = await self.read_conn.execute_fetchall(_SQL_LIST_ACTIVE, (limit,))
        return [ProfileEntry.model_validate(_row_dict(row)) for row in rows]

    async def get(self, entry_id: int) -> ProfileEntry | None:
        rows = await self.read_conn.execute_fetchall(_SQL_GET, (entry_id,))
        return ProfileEntry.model_validate(_row_dict(rows[0])) if rows else None

    async def create(
        self,
        *,
        kind: FactKind,
        summary: str,
        source_fact_ids: list[int] | None = None,
        source_observation_ids: list[int] | None = None,
        created_by: str = "manual",
        policy_version: str = "manual",
        confidence: float = 1.0,
    ) -> ProfileEntry:
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_INSERT,
            (
                kind.value,
                summary,
                json.dumps(source_fact_ids or []),
                json.dumps(source_observation_ids or []),
                now.isoformat(),
                now.isoformat(),
                created_by,
                policy_version,
                confidence,
            ),
        )
        return ProfileEntry(
            id=cursor.lastrowid,
            kind=kind,
            summary=summary,
            source_fact_ids=source_fact_ids or [],
            source_observation_ids=source_observation_ids or [],
            created_at=now,
            updated_at=now,
            created_by=created_by,
            policy_version=policy_version,
            confidence=confidence,
        )

    async def update(
        self,
        entry_id: int,
        *,
        kind: FactKind,
        summary: str,
        source_fact_ids: list[int],
        source_observation_ids: list[int],
        policy_version: str,
        confidence: float,
    ) -> ProfileEntry | None:
        now = datetime.now(UTC)
        cursor = await self.conn.execute(
            _SQL_UPDATE,
            (
                kind.value,
                summary,
                json.dumps(source_fact_ids),
                json.dumps(source_observation_ids),
                now.isoformat(),
                policy_version,
                confidence,
                entry_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        rows = await self.conn.execute_fetchall(_SQL_GET, (entry_id,))
        return ProfileEntry.model_validate(_row_dict(rows[0])) if rows else None

    async def archive(self, entry_id: int) -> bool:
        now = datetime.now(UTC).isoformat()
        cursor = await self.conn.execute(_SQL_ARCHIVE, (now, now, entry_id))
        return cursor.rowcount > 0
