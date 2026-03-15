import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite
from pydantic import BaseModel

from ntrp.context.models import ChatMessage, SessionData, SessionState

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

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT,
    created_at TIMESTAMP NOT NULL,
    message_index INTEGER NOT NULL,
    UNIQUE(session_id, message_index)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, message_index);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at DESC);
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

SQL_CHAT_MAX_INDEX = "SELECT MAX(message_index) FROM chat_messages WHERE session_id = ?"

SQL_INSERT_CHAT_MESSAGE = """
    INSERT INTO chat_messages (session_id, role, content, created_at, message_index)
    VALUES (?, ?, ?, ?, ?)
"""

SQL_GET_CHAT_SLICE = """
    SELECT * FROM chat_messages
    WHERE session_id = ? AND message_index >= ? AND message_index < ?
    ORDER BY message_index
"""

SQL_BACKFILL_CANDIDATES = """
    SELECT s.session_id, s.messages, s.last_activity FROM sessions s
    WHERE s.messages IS NOT NULL AND s.messages != '[]'
    AND NOT EXISTS (SELECT 1 FROM chat_messages cm WHERE cm.session_id = s.session_id)
"""

SQL_LOAD_SESSION = "SELECT * FROM sessions WHERE session_id = ?"
SQL_DELETE_STALE_MESSAGES = "DELETE FROM chat_messages WHERE session_id = ? AND message_index >= ?"
SQL_UPDATE_NAME = "UPDATE sessions SET name = ? WHERE session_id = ?"
SQL_ARCHIVE = "UPDATE sessions SET archived_at = ? WHERE session_id = ? AND archived_at IS NULL"
SQL_RESTORE = "UPDATE sessions SET archived_at = NULL WHERE session_id = ? AND archived_at IS NOT NULL"
SQL_DELETE_ARCHIVED = "DELETE FROM sessions WHERE session_id = ? AND archived_at IS NOT NULL"


class SessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

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
        backfilled = await self.backfill_chat_messages()
        if backfilled:
            from ntrp.logging import get_logger

            get_logger(__name__).info("Backfilled %d chat messages from existing sessions", backfilled)

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
        await self._sync_chat_messages(state.session_id, serializable_messages)
        await self.conn.commit()

    async def _sync_chat_messages(self, session_id: str, messages: list[dict]) -> None:
        rows = await self.conn.execute_fetchall(SQL_CHAT_MAX_INDEX, (session_id,))
        max_existing = rows[0][0] if rows and rows[0][0] is not None else -1

        # Handle revert: if messages list is shorter than what's stored, trim stale rows
        if max_existing >= len(messages):
            await self.conn.execute(SQL_DELETE_STALE_MESSAGES, (session_id, len(messages)))
            max_existing = len(messages) - 1

        now = datetime.now(UTC)
        for idx, msg in enumerate(messages):
            if idx <= max_existing:
                continue
            role = msg.get("role", "")
            content = msg.get("content") if role in ("user", "assistant", "tool") else None
            await self.conn.execute(
                SQL_INSERT_CHAT_MESSAGE,
                (session_id, role, content, now.isoformat(), idx),
            )

    async def load_session(self, session_id: str) -> SessionData | None:
        rows = await self.conn.execute_fetchall(SQL_LOAD_SESSION, (session_id,))
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
        if not (session_id := await self.get_latest_id()):
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
        return await self._update(SQL_UPDATE_NAME, (name, session_id))

    async def archive_session(self, session_id: str) -> bool:
        return await self._update(SQL_ARCHIVE, (datetime.now(UTC).isoformat(), session_id))

    async def restore_session(self, session_id: str) -> bool:
        return await self._update(SQL_RESTORE, (session_id,))

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
        return await self._update(SQL_DELETE_ARCHIVED, (session_id,))

    async def get_chat_slice(self, session_id: str, start_index: int, end_index: int) -> list[ChatMessage]:
        rows = await self.conn.execute_fetchall(SQL_GET_CHAT_SLICE, (session_id, start_index, end_index))
        return [
            ChatMessage(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                created_at=datetime.fromisoformat(r["created_at"]),
                message_index=r["message_index"],
            )
            for r in rows
        ]

    async def backfill_chat_messages(self) -> int:
        """Populate chat_messages from existing session JSON blobs. Runs once."""
        rows = await self.conn.execute_fetchall(SQL_BACKFILL_CANDIDATES)
        if not rows:
            return 0

        count = 0
        for row in rows:
            session_time = row["last_activity"] or datetime.now(UTC).isoformat()
            messages = json.loads(row["messages"])
            for idx, msg in enumerate(messages):
                role = msg.get("role", "")
                content = msg.get("content") if role in ("user", "assistant", "tool") else None
                await self.conn.execute(
                    SQL_INSERT_CHAT_MESSAGE,
                    (row["session_id"], role, content, session_time, idx),
                )
                count += 1
        await self.conn.commit()
        return count
