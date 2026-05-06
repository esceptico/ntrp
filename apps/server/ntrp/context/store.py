import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite
from pydantic import BaseModel

from ntrp.context.models import SessionData, SessionState

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    messages TEXT,
    metadata TEXT,
    name TEXT,
    archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(last_activity);
CREATE INDEX IF NOT EXISTS idx_sessions_archived ON sessions(archived_at);
"""

SQL_SAVE_SESSION = """
INSERT INTO sessions (session_id, started_at, last_activity, messages, metadata, name)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(session_id) DO UPDATE SET
    last_activity = excluded.last_activity,
    messages = excluded.messages,
    metadata = excluded.metadata,
    name = excluded.name
"""

SQL_GET_LATEST = """
SELECT session_id FROM sessions
WHERE archived_at IS NULL
ORDER BY last_activity DESC LIMIT 1
"""

SQL_LIST_SESSIONS = """
SELECT session_id, started_at, last_activity, name,
       json_array_length(COALESCE(messages, '[]')) AS message_count
FROM sessions
WHERE archived_at IS NULL
ORDER BY last_activity DESC
LIMIT ?
"""

SQL_LIST_ARCHIVED = """
SELECT session_id, started_at, last_activity, name, archived_at,
       json_array_length(COALESCE(messages, '[]')) AS message_count
FROM sessions
WHERE archived_at IS NOT NULL
ORDER BY archived_at DESC
LIMIT ?
"""

SQL_LOAD_SESSION = "SELECT * FROM sessions WHERE session_id = ?"
SQL_UPDATE_PROGRESS = """
UPDATE sessions
SET messages = ?, last_activity = ?
WHERE session_id = ?
"""
SQL_UPDATE_NAME = "UPDATE sessions SET name = ? WHERE session_id = ?"
SQL_ARCHIVE = "UPDATE sessions SET archived_at = ? WHERE session_id = ? AND archived_at IS NULL"
SQL_RESTORE = "UPDATE sessions SET archived_at = NULL WHERE session_id = ? AND archived_at IS NOT NULL"
SQL_DELETE_ARCHIVED = "DELETE FROM sessions WHERE session_id = ? AND archived_at IS NOT NULL"


class SessionStore:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn

    async def _update(self, sql: str, params: tuple) -> bool:
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cursor.rowcount > 0

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        for col in ("name TEXT", "archived_at TEXT"):
            try:
                await self.conn.execute(f"ALTER TABLE sessions ADD COLUMN {col}")
                await self.conn.commit()
            except Exception:
                pass

    async def update_progress(self, session_id: str, messages: list[dict | Any]) -> None:
        """Lightweight mid-run save: rewrite messages + bump last_activity,
        leave name/metadata alone. Lets `loadHistory` return the in-flight
        state when a client navigates back to a streaming session."""
        serializable: list[dict] = []
        for msg in messages:
            if isinstance(msg, BaseModel):
                serializable.append(msg.model_dump())
            elif isinstance(msg, dict):
                serializable.append(msg)

        now = datetime.now(UTC).isoformat()
        for msg in serializable:
            if not msg.get("created_at"):
                msg["created_at"] = now

        messages_json = await asyncio.to_thread(lambda: json.dumps(serializable, default=str))
        await self.conn.execute(SQL_UPDATE_PROGRESS, (messages_json, now, session_id))
        await self.conn.commit()

    async def save_session(self, state: SessionState, messages: list[dict | Any], metadata: dict | None = None) -> None:
        serializable_messages: list[dict] = []
        for msg in messages:
            if isinstance(msg, BaseModel):
                serializable_messages.append(msg.model_dump())
            elif isinstance(msg, dict):
                serializable_messages.append(msg)

        # Stamp created_at on every message that hasn't been stamped yet.
        # The list is shared with the agent's in-memory context so the
        # stamp persists across saves without a side-table lookup.
        now = datetime.now(UTC).isoformat()
        for msg in serializable_messages:
            if not msg.get("created_at"):
                msg["created_at"] = now

        meta = metadata or {}
        messages_json, metadata_json = await asyncio.to_thread(
            lambda: (json.dumps(serializable_messages, default=str), json.dumps(meta))
        )
        await self.conn.execute(
            SQL_SAVE_SESSION,
            (
                state.session_id,
                state.started_at.isoformat(),
                state.last_activity.isoformat(),
                messages_json,
                metadata_json,
                state.name,
            ),
        )
        await self.conn.commit()

    async def load_session(self, session_id: str) -> SessionData | None:
        rows = await self.read_conn.execute_fetchall(SQL_LOAD_SESSION, (session_id,))
        if not rows:
            return None

        row = rows[0]
        started_at = datetime.fromisoformat(row["started_at"])
        last_activity = datetime.fromisoformat(row["last_activity"])
        # Attach UTC to naive datetimes from old sessions
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=UTC)

        name = row["name"]

        state = SessionState(
            session_id=row["session_id"],
            started_at=started_at,
            last_activity=last_activity,
            name=name,
        )

        raw_messages, raw_metadata = row["messages"], row["metadata"]
        messages, metadata = await asyncio.to_thread(
            lambda: (json.loads(raw_messages) if raw_messages else [], json.loads(raw_metadata) if raw_metadata else {})
        )
        return SessionData(
            state=state,
            messages=messages,
            last_input_tokens=metadata.get("last_input_tokens"),
        )

    async def get_latest_id(self) -> str | None:
        rows = await self.read_conn.execute_fetchall(SQL_GET_LATEST)
        return rows[0]["session_id"] if rows else None

    async def get_latest_session(self) -> SessionData | None:
        if not (session_id := await self.get_latest_id()):
            return None
        return await self.load_session(session_id)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        rows = await self.read_conn.execute_fetchall(SQL_LIST_SESSIONS, (limit,))
        return [
            {
                "session_id": row["session_id"],
                "started_at": row["started_at"],
                "last_activity": row["last_activity"],
                "name": row["name"],
                "message_count": row["message_count"],
            }
            for row in rows
        ]

    async def update_session_name(self, session_id: str, name: str) -> bool:
        return await self._update(SQL_UPDATE_NAME, (name, session_id))

    async def archive_session(self, session_id: str) -> bool:
        return await self._update(SQL_ARCHIVE, (datetime.now(UTC).isoformat(), session_id))

    async def restore_session(self, session_id: str) -> bool:
        return await self._update(SQL_RESTORE, (session_id,))

    async def list_archived_sessions(self, limit: int = 20) -> list[dict]:
        rows = await self.read_conn.execute_fetchall(SQL_LIST_ARCHIVED, (limit,))
        return [
            {
                "session_id": row["session_id"],
                "started_at": row["started_at"],
                "last_activity": row["last_activity"],
                "name": row["name"],
                "message_count": row["message_count"],
                "archived_at": row["archived_at"],
            }
            for row in rows
        ]

    async def permanently_delete_session(self, session_id: str) -> bool:
        return await self._update(SQL_DELETE_ARCHIVED, (session_id,))
