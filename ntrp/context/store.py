import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ntrp.context.models import SessionData, SessionState
from ntrp.database import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    current_task TEXT,
    rolling_summary TEXT,
    last_compaction_turn INTEGER DEFAULT 0,
    messages TEXT,
    gathered_context TEXT,
    pending_actions TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(last_activity);
"""


class SessionDatabase(Database):
    async def connect(self) -> None:
        await super().connect()
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()


class SessionStore(SessionDatabase):
    async def save_session(self, state: SessionState, messages: list[dict | Any]) -> None:
        serializable_messages = []
        for msg in messages:
            if isinstance(msg, BaseModel):
                serializable_messages.append(msg.model_dump())
            elif isinstance(msg, dict):
                serializable_messages.append(msg)

        await self.conn.execute(
            """
            INSERT OR REPLACE INTO sessions (
                session_id, user_id, started_at, last_activity,
                current_task, rolling_summary, last_compaction_turn,
                messages, gathered_context, pending_actions, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.session_id,
                state.user_id,
                state.started_at.isoformat(),
                state.last_activity.isoformat(),
                state.current_task,
                state.rolling_summary,
                state.last_compaction_turn,
                json.dumps(serializable_messages, default=str),
                json.dumps(state.gathered_context, default=str),
                json.dumps(state.pending_actions, default=str),
                json.dumps({}),
            ),
        )
        await self.conn.commit()

    async def load_session(self, session_id: str) -> SessionData | None:
        rows = await self.conn.execute_fetchall("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        if not rows:
            return None

        row = rows[0]
        state = SessionState(
            session_id=row["session_id"],
            user_id=row["user_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            last_activity=datetime.fromisoformat(row["last_activity"]),
            current_task=row["current_task"],
            rolling_summary=row["rolling_summary"] or "",
            last_compaction_turn=row["last_compaction_turn"] or 0,
            gathered_context=json.loads(row["gathered_context"]) if row["gathered_context"] else [],
            pending_actions=json.loads(row["pending_actions"]) if row["pending_actions"] else [],
        )

        messages = json.loads(row["messages"]) if row["messages"] else []
        return SessionData(state=state, messages=messages)

    async def get_latest_session(self, user_id: str = "local") -> SessionData | None:
        rows = await self.conn.execute_fetchall(
            """SELECT session_id FROM sessions
               WHERE user_id = ?
               ORDER BY last_activity DESC LIMIT 1""",
            (user_id,),
        )
        if not rows:
            return None
        return await self.load_session(rows[0]["session_id"])

    async def list_sessions(self, user_id: str = "local", limit: int = 10) -> list[dict]:
        rows = await self.conn.execute_fetchall(
            """SELECT session_id, started_at, last_activity, rolling_summary
               FROM sessions
               WHERE user_id = ?
               ORDER BY last_activity DESC
               LIMIT ?""",
            (user_id, limit),
        )
        return [
            {
                "session_id": row["session_id"],
                "started_at": row["started_at"],
                "last_activity": row["last_activity"],
                "summary": (row["rolling_summary"] or "")[:100],
            }
            for row in rows
        ]

    async def delete_session(self, session_id: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def cleanup_old_sessions(self, days: int = 30) -> int:
        cutoff = datetime.now().isoformat()
        cursor = await self.conn.execute(
            """DELETE FROM sessions
               WHERE last_activity < datetime(?, ?)""",
            (cutoff, f"-{days} days"),
        )
        await self.conn.commit()
        return cursor.rowcount
