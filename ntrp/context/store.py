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
    name TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(last_activity);
"""

SQL_SAVE_SESSION = """
INSERT OR REPLACE INTO sessions (
    session_id, started_at, last_activity,
    messages, metadata, name, archived_at
) VALUES (?, ?, ?, ?, ?, ?, NULL)
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


class SessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        for col in ("name TEXT", "archived_at TEXT"):
            try:
                await self.conn.execute(f"ALTER TABLE sessions ADD COLUMN {col}")
                await self.conn.commit()
            except Exception:
                pass

    async def save_session(self, state: SessionState, messages: list[dict | Any], metadata: dict | None = None) -> None:
        serializable_messages = []
        for msg in messages:
            if isinstance(msg, BaseModel):
                serializable_messages.append(msg.model_dump())
            elif isinstance(msg, dict):
                serializable_messages.append(msg)

        await self.conn.execute(
            SQL_SAVE_SESSION,
            (
                state.session_id,
                state.started_at.isoformat(),
                state.last_activity.isoformat(),
                json.dumps(serializable_messages, default=str),
                json.dumps(metadata or {}),
                state.name,
            ),
        )
        await self.conn.commit()

    async def load_session(self, session_id: str) -> SessionData | None:
        rows = await self.conn.execute_fetchall("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
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

        messages = json.loads(row["messages"]) if row["messages"] else []
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        return SessionData(
            state=state,
            messages=messages,
            last_input_tokens=metadata.get("last_input_tokens"),
        )

    async def get_latest_id(self) -> str | None:
        rows = await self.conn.execute_fetchall(SQL_GET_LATEST)
        return rows[0]["session_id"] if rows else None

    async def get_latest_session(self) -> SessionData | None:
        session_id = await self.get_latest_id()
        if not session_id:
            return None
        return await self.load_session(session_id)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        rows = await self.conn.execute_fetchall(SQL_LIST_SESSIONS, (limit,))
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
        cursor = await self.conn.execute(
            "UPDATE sessions SET name = ? WHERE session_id = ?",
            (name, session_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def archive_session(self, session_id: str) -> bool:
        cursor = await self.conn.execute(
            "UPDATE sessions SET archived_at = ? WHERE session_id = ? AND archived_at IS NULL",
            (datetime.now(UTC).isoformat(), session_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def restore_session(self, session_id: str) -> bool:
        cursor = await self.conn.execute(
            "UPDATE sessions SET archived_at = NULL WHERE session_id = ? AND archived_at IS NOT NULL",
            (session_id,),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def list_archived_sessions(self, limit: int = 20) -> list[dict]:
        rows = await self.conn.execute_fetchall(SQL_LIST_ARCHIVED, (limit,))
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
        cursor = await self.conn.execute(
            "DELETE FROM sessions WHERE session_id = ? AND archived_at IS NOT NULL",
            (session_id,),
        )
        await self.conn.commit()
        return cursor.rowcount > 0
