import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel

from ntrp.constants import SESSION_HANDOFF_MARKER
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

CREATE TABLE IF NOT EXISTS session_messages (
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    message_json TEXT NOT NULL,
    client_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, message_id),
    UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_session_messages_session_seq
    ON session_messages(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_session_messages_client
    ON session_messages(session_id, client_id);

CREATE TABLE IF NOT EXISTS session_episodes (
    session_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    user_message_id TEXT NOT NULL,
    message_start_id TEXT NOT NULL,
    message_end_id TEXT NOT NULL,
    message_start_seq INTEGER NOT NULL,
    message_end_seq INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    PRIMARY KEY (session_id, episode_id),
    UNIQUE (session_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_session_episodes_session_turn
    ON session_episodes(session_id, turn_index);
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
# Upsert: a fresh session won't have a row yet on its very first save,
# and an UPDATE-only would silently no-op (lost user message until the
# final end-of-run save).
SQL_UPSERT_PROGRESS = """
INSERT INTO sessions (session_id, started_at, last_activity, messages, metadata, name)
VALUES (?, ?, ?, ?, '{}', ?)
ON CONFLICT(session_id) DO UPDATE SET
    messages = excluded.messages,
    last_activity = excluded.last_activity
"""
SQL_UPDATE_NAME = "UPDATE sessions SET name = ? WHERE session_id = ?"
SQL_ARCHIVE = "UPDATE sessions SET archived_at = ? WHERE session_id = ? AND archived_at IS NULL"
SQL_RESTORE = "UPDATE sessions SET archived_at = NULL WHERE session_id = ? AND archived_at IS NOT NULL"
SQL_DELETE_ARCHIVED = "DELETE FROM sessions WHERE session_id = ? AND archived_at IS NOT NULL"

SQL_LOAD_SESSION_MESSAGES_COUNT = "SELECT 1 FROM session_messages WHERE session_id = ? LIMIT 1"
SQL_LOAD_SESSION_MESSAGES_JSON = "SELECT messages FROM sessions WHERE session_id = ?"


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

    def _to_serializable_messages(self, messages: list[dict | Any]) -> list[dict]:
        serializable: list[dict] = []
        for msg in messages:
            if isinstance(msg, BaseModel):
                serializable.append(msg.model_dump())
            elif isinstance(msg, dict):
                serializable.append(msg)
        return serializable

    def _stamp_messages(self, messages: list[dict], now: str) -> None:
        seen: set[str] = set()
        for msg in messages:
            if not msg.get("created_at"):
                msg["created_at"] = now

            message_id = msg.get("message_id") or msg.get("client_id")
            if not isinstance(message_id, str) or not message_id or message_id in seen:
                message_id = f"msg-{uuid4().hex[:16]}"
            msg["message_id"] = message_id
            seen.add(message_id)

    async def _mirror_session_messages(self, session_id: str, messages: list[dict]) -> None:
        if not messages:
            await self.conn.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
            await self.conn.execute("DELETE FROM session_episodes WHERE session_id = ?", (session_id,))
            return

        rows = await self.conn.execute_fetchall(
            "SELECT message_id, seq FROM session_messages WHERE session_id = ?",
            (session_id,),
        )
        existing = {row["message_id"]: row["seq"] for row in rows}
        next_seq = max(existing.values(), default=-1) + 1

        for msg in messages:
            message_id = msg.get("message_id")
            if not isinstance(message_id, str) or not message_id:
                continue

            role = str(msg.get("role") or "")
            client_id = msg.get("client_id") if isinstance(msg.get("client_id"), str) else None
            created_at = str(msg.get("created_at") or datetime.now(UTC).isoformat())
            message_json = await asyncio.to_thread(lambda m=msg: json.dumps(m, default=str))

            if message_id in existing:
                await self.conn.execute(
                    """
                    UPDATE session_messages
                    SET role = ?, message_json = ?, client_id = ?, created_at = ?
                    WHERE session_id = ? AND message_id = ?
                    """,
                    (role, message_json, client_id, created_at, session_id, message_id),
                )
            else:
                await self.conn.execute(
                    """
                    INSERT INTO session_messages
                        (session_id, message_id, seq, role, message_json, client_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, message_id, next_seq, role, message_json, client_id, created_at),
                )
                next_seq += 1
        await self._rebuild_session_episodes(session_id)

    def _message_row_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "message_id": row["message_id"],
            "seq": row["seq"],
            "role": row["role"],
            "client_id": row["client_id"],
            "created_at": row["created_at"],
            "message": json.loads(row["message_json"]),
        }

    def _is_episode_message(self, row: aiosqlite.Row) -> bool:
        if row["role"] == "system":
            return False
        message = json.loads(row["message_json"])
        content = message.get("content", "")
        return not (isinstance(content, str) and content.startswith(SESSION_HANDOFF_MARKER))

    async def _rebuild_session_episodes(self, session_id: str) -> None:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM session_messages WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        )
        await self.conn.execute("DELETE FROM session_episodes WHERE session_id = ?", (session_id,))

        current_start: aiosqlite.Row | None = None
        current_end: aiosqlite.Row | None = None
        turn_index = 0

        async def flush_current() -> None:
            nonlocal current_start, current_end, turn_index
            if current_start is None or current_end is None:
                return
            episode_id = f"{session_id}:{turn_index}"
            await self.conn.execute(
                """
                INSERT INTO session_episodes (
                    session_id, episode_id, turn_index, user_message_id,
                    message_start_id, message_end_id, message_start_seq, message_end_seq,
                    started_at, ended_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    episode_id,
                    turn_index,
                    current_start["message_id"],
                    current_start["message_id"],
                    current_end["message_id"],
                    current_start["seq"],
                    current_end["seq"],
                    current_start["created_at"],
                    current_end["created_at"],
                ),
            )
            turn_index += 1
            current_start = None
            current_end = None

        for row in rows:
            if not self._is_episode_message(row):
                continue
            if row["role"] == "user":
                await flush_current()
                current_start = row
            if current_start is not None:
                current_end = row

        await flush_current()

    async def _ensure_session_messages(self, session_id: str) -> None:
        has_rows = await self.read_conn.execute_fetchall(SQL_LOAD_SESSION_MESSAGES_COUNT, (session_id,))
        if has_rows:
            return

        rows = await self.read_conn.execute_fetchall(SQL_LOAD_SESSION_MESSAGES_JSON, (session_id,))
        if not rows or not rows[0]["messages"]:
            return

        messages = await asyncio.to_thread(lambda: json.loads(rows[0]["messages"]))
        if not isinstance(messages, list) or not messages:
            return

        now = datetime.now(UTC).isoformat()
        serializable = [msg for msg in messages if isinstance(msg, dict)]
        self._stamp_messages(serializable, now)
        messages_json = await asyncio.to_thread(lambda: json.dumps(serializable, default=str))
        await self._mirror_session_messages(session_id, serializable)
        await self.conn.execute("UPDATE sessions SET messages = ? WHERE session_id = ?", (messages_json, session_id))
        await self.conn.commit()

    async def update_progress(self, state: SessionState, messages: list[dict | Any]) -> None:
        """Lightweight mid-run save: rewrite messages + bump last_activity,
        upserting the row so a fresh session's first save lands instead of
        silently no-op'ing. Leaves metadata alone — the final save in the
        chat service re-stamps last_input_tokens."""
        serializable = self._to_serializable_messages(messages)
        now = datetime.now(UTC).isoformat()
        self._stamp_messages(serializable, now)

        messages_json = await asyncio.to_thread(lambda: json.dumps(serializable, default=str))
        await self.conn.execute(
            SQL_UPSERT_PROGRESS,
            (
                state.session_id,
                state.started_at.isoformat(),
                now,
                messages_json,
                state.name,
            ),
        )
        await self._mirror_session_messages(state.session_id, serializable)
        await self.conn.commit()

    async def save_session(self, state: SessionState, messages: list[dict | Any], metadata: dict | None = None) -> None:
        serializable_messages = self._to_serializable_messages(messages)

        # Stamp created_at on every message that hasn't been stamped yet.
        # The list is shared with the agent's in-memory context so the
        # stamp persists across saves without a side-table lookup.
        now = datetime.now(UTC).isoformat()
        self._stamp_messages(serializable_messages, now)

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
        await self._mirror_session_messages(state.session_id, serializable_messages)
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

    async def list_session_messages(
        self,
        session_id: str,
        limit: int = 100,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
        around_seq: int | None = None,
    ) -> dict:
        await self._ensure_session_messages(session_id)
        limit = max(1, min(limit, 250))

        async def seq_for_message(ref: str | None) -> int | None:
            if not ref:
                return None
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT seq FROM session_messages
                WHERE session_id = ? AND (message_id = ? OR client_id = ?)
                LIMIT 1
                """,
                (session_id, ref, ref),
            )
            return int(rows[0]["seq"]) if rows else None

        rows: list[Any]
        around_at = await seq_for_message(around)
        before_at = await seq_for_message(before)
        after_at = await seq_for_message(after)
        if around_seq is not None:
            start = max(0, around_seq - (limit // 2))
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM session_messages
                WHERE session_id = ? AND seq >= ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (session_id, start, limit),
            )
        elif around_at is not None:
            start = max(0, around_at - (limit // 2))
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM session_messages
                WHERE session_id = ? AND seq >= ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (session_id, start, limit),
            )
        elif before_at is not None:
            desc_rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM session_messages
                WHERE session_id = ? AND seq < ?
                ORDER BY seq DESC
                LIMIT ?
                """,
                (session_id, before_at, limit),
            )
            rows = list(reversed(desc_rows))
        elif after_at is not None:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM session_messages
                WHERE session_id = ? AND seq > ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (session_id, after_at, limit),
            )
        else:
            desc_rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM session_messages
                WHERE session_id = ?
                ORDER BY seq DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = list(reversed(desc_rows))

        messages = [
            self._message_row_payload(row)
            for row in rows
        ]
        first_seq = messages[0]["seq"] if messages else None
        last_seq = messages[-1]["seq"] if messages else None
        has_more_before = False
        has_more_after = False
        if first_seq is not None:
            has_more_before = bool(
                await self.read_conn.execute_fetchall(
                    "SELECT 1 FROM session_messages WHERE session_id = ? AND seq < ? LIMIT 1",
                    (session_id, first_seq),
                )
            )
        if last_seq is not None:
            has_more_after = bool(
                await self.read_conn.execute_fetchall(
                    "SELECT 1 FROM session_messages WHERE session_id = ? AND seq > ? LIMIT 1",
                    (session_id, last_seq),
                )
            )

        return {
            "messages": messages,
            "has_more_before": has_more_before,
            "has_more_after": has_more_after,
            "before": messages[0]["message_id"] if messages else None,
            "after": messages[-1]["message_id"] if messages else None,
        }

    async def delete_session_messages_from(
        self,
        session_id: str,
        message_id: str | None = None,
        seq: int | None = None,
    ) -> bool:
        await self._ensure_session_messages(session_id)
        target_seq = seq
        if target_seq is None and message_id:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT seq FROM session_messages
                WHERE session_id = ? AND (message_id = ? OR client_id = ?)
                LIMIT 1
                """,
                (session_id, message_id, message_id),
            )
            target_seq = int(rows[0]["seq"]) if rows else None
        if target_seq is None:
            return False

        cursor = await self.conn.execute(
            "DELETE FROM session_messages WHERE session_id = ? AND seq >= ?",
            (session_id, target_seq),
        )
        await self._rebuild_session_episodes(session_id)
        await self.conn.commit()
        return cursor.rowcount > 0

    async def list_session_episodes(self, session_id: str, limit: int = 100) -> list[dict]:
        await self._ensure_session_messages(session_id)
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT *
            FROM session_episodes
            WHERE session_id = ?
            ORDER BY turn_index ASC
            LIMIT ?
            """,
            (session_id, max(1, min(limit, 500))),
        )
        return [
            {
                "session_id": row["session_id"],
                "episode_id": row["episode_id"],
                "turn_index": row["turn_index"],
                "user_message_id": row["user_message_id"],
                "message_start_id": row["message_start_id"],
                "message_end_id": row["message_end_id"],
                "message_start_seq": row["message_start_seq"],
                "message_end_seq": row["message_end_seq"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
            }
            for row in rows
        ]
