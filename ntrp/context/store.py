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
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(last_activity);
"""

SQL_SAVE_SESSION = """
INSERT OR REPLACE INTO sessions (
    session_id, started_at, last_activity,
    messages, metadata
) VALUES (?, ?, ?, ?, ?)
"""

SQL_GET_LATEST = """
SELECT session_id FROM sessions
ORDER BY last_activity DESC LIMIT 1
"""

SQL_LIST_SESSIONS = """
SELECT session_id, started_at, last_activity
FROM sessions
ORDER BY last_activity DESC
LIMIT ?
"""


class SessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def save_session(self, state: SessionState, messages: list[dict | Any]) -> None:
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
                json.dumps({}),
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
        state = SessionState(
            session_id=row["session_id"],
            started_at=started_at,
            last_activity=last_activity,
        )

        messages = json.loads(row["messages"]) if row["messages"] else []
        return SessionData(state=state, messages=messages)

    async def get_latest_session(self) -> SessionData | None:
        rows = await self.conn.execute_fetchall(SQL_GET_LATEST)
        if not rows:
            return None
        return await self.load_session(rows[0]["session_id"])

    async def list_sessions(self, limit: int = 10) -> list[dict]:
        rows = await self.conn.execute_fetchall(SQL_LIST_SESSIONS, (limit,))
        return [
            {
                "session_id": row["session_id"],
                "started_at": row["started_at"],
                "last_activity": row["last_activity"],
            }
            for row in rows
        ]

    async def delete_session(self, session_id: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await self.conn.commit()
        return cursor.rowcount > 0
