import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel

from ntrp.constants import SESSION_HANDOFF_MARKER
from ntrp.context.models import SessionData, SessionState
from ntrp.events.sse import event_from_payload
from ntrp.server.bus import StreamRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    messages TEXT,
    metadata TEXT,
    name TEXT,
    archived_at TEXT,
    session_type TEXT NOT NULL DEFAULT 'chat',
    origin_automation_id TEXT
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

CREATE TABLE IF NOT EXISTS session_turns (
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    user_message_id TEXT NOT NULL,
    message_start_id TEXT NOT NULL,
    message_end_id TEXT NOT NULL,
    message_start_seq INTEGER NOT NULL,
    message_end_seq INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    PRIMARY KEY (session_id, turn_id),
    UNIQUE (session_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_session_turns_session_turn
    ON session_turns(session_id, turn_index);

CREATE TABLE IF NOT EXISTS chat_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    stop_reason TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ended_at TEXT,
    last_seq INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    error_message TEXT,
    client_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_runs_session_status
    ON chat_runs(session_id, status);

CREATE TABLE IF NOT EXISTS chat_queued_messages (
    client_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    message_json TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ingested_at TEXT,
    enqueued_seq INTEGER,
    ingested_seq INTEGER
);

CREATE INDEX IF NOT EXISTS idx_chat_queued_messages_session_status
    ON chat_queued_messages(session_id, status);
CREATE INDEX IF NOT EXISTS idx_chat_queued_messages_run_status
    ON chat_queued_messages(run_id, status);

CREATE TABLE IF NOT EXISTS chat_idempotency_keys (
    session_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    run_id TEXT,
    message_id TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    PRIMARY KEY (session_id, client_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_idempotency_run
    ON chat_idempotency_keys(run_id);
CREATE INDEX IF NOT EXISTS idx_chat_idempotency_expires
    ON chat_idempotency_keys(expires_at);

CREATE TABLE IF NOT EXISTS tool_calls (
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    action TEXT NOT NULL,
    scope TEXT NOT NULL,
    args_hash TEXT,
    status TEXT NOT NULL,
    result_preview TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    PRIMARY KEY (run_id, tool_call_id)
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_run
    ON tool_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session_started
    ON tool_calls(session_id, started_at);

CREATE TABLE IF NOT EXISTS tool_approvals (
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    action TEXT NOT NULL,
    scope TEXT NOT NULL,
    preview TEXT,
    diff TEXT,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    resolved_at TEXT,
    expires_at TEXT,
    result_feedback TEXT,
    PRIMARY KEY (run_id, tool_call_id)
);

CREATE INDEX IF NOT EXISTS idx_tool_approvals_run
    ON tool_approvals(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_approvals_session_status
    ON tool_approvals(session_id, status);

CREATE TABLE IF NOT EXISTS session_events (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_json TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_session_events_session_seq
    ON session_events(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_session_events_run
    ON session_events(run_id);

CREATE TABLE IF NOT EXISTS chat_compactions (
    compaction_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    boundary_seq INTEGER NOT NULL,
    messages_before INTEGER NOT NULL,
    messages_after INTEGER NOT NULL,
    rehydration_state TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_compactions_session_boundary
    ON chat_compactions(session_id, boundary_seq);

CREATE TABLE IF NOT EXISTS background_agent_runs (
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    parent_run_id TEXT,
    status TEXT NOT NULL,
    command TEXT NOT NULL,
    detail TEXT,
    result_ref TEXT,
    result_text TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    ended_at TEXT,
    cancel_requested_at TEXT,
    notified_at TEXT,
    PRIMARY KEY (session_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_background_agent_runs_session_status
    ON background_agent_runs(session_id, status);

CREATE TABLE IF NOT EXISTS background_agent_events (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    result_ref TEXT,
    terminal INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_background_agent_events_task
    ON background_agent_events(task_id);

CREATE TABLE IF NOT EXISTS session_goals (
    session_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'paused', 'blocked', 'budget_limited', 'complete')),
    evidence_json TEXT NOT NULL DEFAULT '[]',
    blocked_reason TEXT,
    token_budget INTEGER,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    time_used_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
		"""

SQL_SAVE_SESSION = """
INSERT INTO sessions (
    session_id, started_at, last_activity, messages, metadata, name,
    session_type, origin_automation_id
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(session_id) DO UPDATE SET
    last_activity = excluded.last_activity,
    messages = excluded.messages,
    metadata = excluded.metadata,
    name = excluded.name,
    session_type = excluded.session_type,
    origin_automation_id = excluded.origin_automation_id
"""

SQL_GET_LATEST = """
SELECT session_id FROM sessions
WHERE archived_at IS NULL
ORDER BY last_activity DESC LIMIT 1
"""

SQL_LIST_SESSIONS = """
SELECT session_id, started_at, last_activity, name,
       session_type, origin_automation_id,
       json_array_length(COALESCE(messages, '[]')) AS message_count
FROM sessions
WHERE archived_at IS NULL
ORDER BY last_activity DESC
LIMIT ?
"""

SQL_LIST_ARCHIVED = """
SELECT session_id, started_at, last_activity, name, archived_at,
       session_type, origin_automation_id,
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
INSERT INTO sessions (
    session_id, started_at, last_activity, messages, metadata, name,
    session_type, origin_automation_id
)
VALUES (?, ?, ?, ?, '{}', ?, ?, ?)
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
CHAT_IDEMPOTENCY_TTL_DAYS = 30
CHAT_IDEMPOTENCY_TERMINAL_STATUSES = ("completed", "cancelled", "error", "failed", "interrupted")


class SessionStore:
    def __init__(self, conn: aiosqlite.Connection, read_conn: aiosqlite.Connection | None = None):
        self.conn = conn
        self.read_conn = read_conn or conn
        self._background_event_lock = asyncio.Lock()
        self._session_locks_guard = asyncio.Lock()
        self._session_write_locks: dict[str, asyncio.Lock] = {}

    async def _session_write_lock(self, session_id: str) -> asyncio.Lock:
        async with self._session_locks_guard:
            lock = self._session_write_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._session_write_locks[session_id] = lock
            return lock

    async def _update(self, sql: str, params: tuple) -> bool:
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cursor.rowcount > 0

    def _chat_run_payload(self, row: aiosqlite.Row) -> dict:
        columns = set(row.keys())
        return {
            "run_id": row["run_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "stop_reason": row["stop_reason"],
            "started_at": row["started_at"],
            "updated_at": row["updated_at"],
            "ended_at": row["ended_at"],
            "last_seq": row["last_seq"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "error_code": row["error_code"] if "error_code" in columns else None,
            "error_message": row["error_message"] if "error_message" in columns else None,
            "client_id": row["client_id"] if "client_id" in columns else None,
        }

    def _chat_queued_message_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "client_id": row["client_id"],
            "session_id": row["session_id"],
            "run_id": row["run_id"],
            "status": row["status"],
            "message": json.loads(row["message_json"]),
            "enqueued_at": row["enqueued_at"],
            "updated_at": row["updated_at"],
            "ingested_at": row["ingested_at"],
            "enqueued_seq": row["enqueued_seq"],
            "ingested_seq": row["ingested_seq"],
        }

    def _chat_idempotency_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "client_id": row["client_id"],
            "request_hash": row["request_hash"],
            "run_id": row["run_id"],
            "message_id": row["message_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
        }

    def _background_agent_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "task_id": row["task_id"],
            "session_id": row["session_id"],
            "parent_run_id": row["parent_run_id"],
            "status": row["status"],
            "command": row["command"],
            "detail": row["detail"],
            "result_ref": row["result_ref"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "updated_at": row["updated_at"],
            "ended_at": row["ended_at"],
            "cancel_requested_at": row["cancel_requested_at"],
            "notified_at": row["notified_at"],
        }

    def _background_agent_event_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "seq": row["seq"],
            "task_id": row["task_id"],
            "status": row["status"],
            "detail": row["detail"],
            "result_ref": row["result_ref"],
            "terminal": bool(row["terminal"]),
            "created_at": row["created_at"],
        }

    def _tool_call_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "run_id": row["run_id"],
            "session_id": row["session_id"],
            "tool_call_id": row["tool_call_id"],
            "tool_name": row["tool_name"],
            "action": row["action"],
            "scope": row["scope"],
            "args_hash": row["args_hash"],
            "status": row["status"],
            "result_preview": row["result_preview"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
        }

    def _tool_approval_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "run_id": row["run_id"],
            "session_id": row["session_id"],
            "tool_call_id": row["tool_call_id"],
            "tool_name": row["tool_name"],
            "action": row["action"],
            "scope": row["scope"],
            "preview": row["preview"],
            "diff": row["diff"],
            "status": row["status"],
            "requested_at": row["requested_at"],
            "resolved_at": row["resolved_at"],
            "expires_at": row["expires_at"],
            "result_feedback": row["result_feedback"],
        }

    def _goal_payload(self, row: aiosqlite.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "goal_id": row["goal_id"],
            "objective": row["objective"],
            "status": row["status"],
            "evidence": json.loads(row["evidence_json"] or "[]"),
            "blocked_reason": row["blocked_reason"],
            "token_budget": row["token_budget"],
            "tokens_used": int(row["tokens_used"] or 0),
            "time_used_seconds": int(row["time_used_seconds"] or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        for col in (
            "name TEXT",
            "archived_at TEXT",
            "session_type TEXT NOT NULL DEFAULT 'chat'",
            "origin_automation_id TEXT",
        ):
            try:
                await self.conn.execute(f"ALTER TABLE sessions ADD COLUMN {col}")
                await self.conn.commit()
            except Exception:
                pass
        await self._migrate_session_turns_schema()
        await self._migrate_tool_calls_schema()
        await self._migrate_background_agent_runs_schema()
        await self._migrate_chat_compactions_schema()
        await self._migrate_chat_runs_schema()
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_idempotency_expires ON chat_idempotency_keys(expires_at)"
        )
        await self.conn.commit()

    async def _migrate_session_turns_schema(self) -> None:
        # Older builds named per-user-turn transcript slices "session_episodes".
        # Keep the data, but store it under the accurate name going forward.
        rows = await self.conn.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'session_episodes'"
        )
        if not rows:
            return
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO session_turns (
                session_id, turn_id, turn_index, user_message_id,
                message_start_id, message_end_id, message_start_seq, message_end_seq,
                started_at, ended_at
            )
            SELECT
                session_id, episode_id, turn_index, user_message_id,
                message_start_id, message_end_id, message_start_seq, message_end_seq,
                started_at, ended_at
            FROM session_episodes
            """
        )
        await self.conn.commit()

    async def set_goal(
        self,
        session_id: str,
        objective: str,
        *,
        token_budget: int | None = None,
    ) -> dict:
        lock = await self._session_write_lock(session_id)
        async with lock:
            return await self._set_goal_unlocked(session_id, objective, token_budget=token_budget)

    async def _set_goal_unlocked(
        self,
        session_id: str,
        objective: str,
        *,
        token_budget: int | None = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        goal_id = uuid4().hex
        await self.conn.execute(
            """
            INSERT INTO session_goals (
                session_id, goal_id, objective, status, evidence_json,
                blocked_reason, token_budget, tokens_used, time_used_seconds,
                created_at, updated_at
            )
            VALUES (?, ?, ?, 'active', '[]', NULL, ?, 0, 0, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                goal_id = excluded.goal_id,
                objective = excluded.objective,
                status = excluded.status,
                evidence_json = excluded.evidence_json,
                blocked_reason = NULL,
                token_budget = excluded.token_budget,
                tokens_used = 0,
                time_used_seconds = 0,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (session_id, goal_id, objective, token_budget, now, now),
        )
        await self.conn.commit()
        goal = await self.get_goal(session_id)
        if goal is None:
            raise RuntimeError("goal insert failed")
        return goal

    async def get_goal(self, session_id: str) -> dict | None:
        rows = await self.read_conn.execute_fetchall(
            "SELECT * FROM session_goals WHERE session_id = ?",
            (session_id,),
        )
        return self._goal_payload(rows[0]) if rows else None

    async def clear_goal(self, session_id: str) -> bool:
        lock = await self._session_write_lock(session_id)
        async with lock:
            cursor = await self.conn.execute("DELETE FROM session_goals WHERE session_id = ?", (session_id,))
            await self.conn.commit()
            return cursor.rowcount > 0

    async def update_goal(
        self,
        session_id: str,
        *,
        goal_id: str | None = None,
        status: str | None = None,
        evidence: str | None = None,
        blocked_reason: str | None = None,
        tokens_used_delta: int = 0,
        time_used_seconds_delta: int = 0,
    ) -> dict | None:
        lock = await self._session_write_lock(session_id)
        async with lock:
            return await self._update_goal_unlocked(
                session_id,
                goal_id=goal_id,
                status=status,
                evidence=evidence,
                blocked_reason=blocked_reason,
                tokens_used_delta=tokens_used_delta,
                time_used_seconds_delta=time_used_seconds_delta,
            )

    async def _update_goal_unlocked(
        self,
        session_id: str,
        *,
        goal_id: str | None = None,
        status: str | None = None,
        evidence: str | None = None,
        blocked_reason: str | None = None,
        tokens_used_delta: int = 0,
        time_used_seconds_delta: int = 0,
    ) -> dict | None:
        current = await self.get_goal(session_id)
        if current is None:
            return None
        if goal_id is not None and current["goal_id"] != goal_id:
            return None
        next_evidence = list(current["evidence"])
        if evidence:
            next_evidence.append({"text": evidence, "created_at": datetime.now(UTC).isoformat()})
        next_status = status or current["status"]
        next_tokens_used = current["tokens_used"] + max(0, tokens_used_delta)
        if (
            status is None
            and current.get("token_budget")
            and next_tokens_used >= current["token_budget"]
            and current["status"] == "active"
        ):
            next_status = "budget_limited"
        next_blocked_reason = blocked_reason if next_status == "blocked" else None
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            UPDATE session_goals
            SET status = ?,
                evidence_json = ?,
                blocked_reason = ?,
                tokens_used = tokens_used + ?,
                time_used_seconds = time_used_seconds + ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                next_status,
                json.dumps(next_evidence),
                next_blocked_reason,
                max(0, tokens_used_delta),
                max(0, time_used_seconds_delta),
                now,
                session_id,
            ),
        )
        await self.conn.commit()
        return await self.get_goal(session_id)

    async def _migrate_chat_compactions_schema(self) -> None:
        rows = await self.conn.execute_fetchall("PRAGMA table_info(chat_compactions)")
        columns = {row["name"] for row in rows}
        if "rehydration_state" in columns:
            return
        await self.conn.execute("ALTER TABLE chat_compactions ADD COLUMN rehydration_state TEXT")
        await self.conn.commit()

    async def _migrate_chat_runs_schema(self) -> None:
        rows = await self.conn.execute_fetchall("PRAGMA table_info(chat_runs)")
        if not rows:
            return
        columns = {row["name"] for row in rows}
        changed = False
        for column in (
            "error_code TEXT",
            "error_message TEXT",
            "client_id TEXT",
        ):
            name = column.split()[0]
            if name in columns:
                continue
            await self.conn.execute(f"ALTER TABLE chat_runs ADD COLUMN {column}")
            changed = True
        if changed:
            await self.conn.commit()

    async def _migrate_tool_calls_schema(self) -> None:
        rows = await self.conn.execute_fetchall("PRAGMA table_info(tool_calls)")
        if not rows:
            return

        pk_columns = [row["name"] for row in sorted(rows, key=lambda row: row["pk"]) if row["pk"]]
        if pk_columns == ["run_id", "tool_call_id"]:
            return

        await self.conn.execute("ALTER TABLE tool_calls RENAME TO tool_calls_old")
        await self.conn.execute(
            """
            CREATE TABLE tool_calls (
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                action TEXT NOT NULL,
                scope TEXT NOT NULL,
                args_hash TEXT,
                status TEXT NOT NULL,
                result_preview TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                PRIMARY KEY (run_id, tool_call_id)
            )
            """
        )
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO tool_calls (
                run_id, session_id, tool_call_id, tool_name, action, scope,
                args_hash, status, result_preview, started_at, ended_at
            )
            SELECT
                run_id, session_id, tool_call_id, tool_name, action, scope,
                args_hash, status, result_preview, started_at, ended_at
            FROM tool_calls_old
            """
        )
        await self.conn.execute("DROP TABLE tool_calls_old")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id)")
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_session_started ON tool_calls(session_id, started_at)"
        )
        await self.conn.commit()

    async def _migrate_background_agent_runs_schema(self) -> None:
        rows = await self.conn.execute_fetchall("PRAGMA table_info(background_agent_runs)")
        if not rows:
            return

        columns = {row["name"] for row in rows}
        pk_columns = [row["name"] for row in sorted(rows, key=lambda row: row["pk"]) if row["pk"]]
        if "result_text" in columns and pk_columns == ["session_id", "task_id"]:
            return

        await self.conn.execute("ALTER TABLE background_agent_runs RENAME TO background_agent_runs_old")
        await self.conn.execute(
            """
            CREATE TABLE background_agent_runs (
                task_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                parent_run_id TEXT,
                status TEXT NOT NULL,
                command TEXT NOT NULL,
                detail TEXT,
                result_ref TEXT,
                result_text TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                ended_at TEXT,
                cancel_requested_at TEXT,
                notified_at TEXT,
                PRIMARY KEY (session_id, task_id)
            )
            """
        )
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO background_agent_runs (
                task_id, session_id, parent_run_id, status, command,
                detail, result_ref, result_text, created_at, started_at,
                updated_at, ended_at, cancel_requested_at, notified_at
            )
            SELECT
                task_id, session_id, parent_run_id, status, command,
                detail, result_ref, NULL, created_at, started_at,
                updated_at, ended_at, cancel_requested_at, notified_at
            FROM background_agent_runs_old
            """
        )
        await self.conn.execute("DROP TABLE background_agent_runs_old")
        await self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_background_agent_runs_session_status
                ON background_agent_runs(session_id, status)
            """
        )
        await self.conn.commit()

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
        # session_messages is the durable UI/debug transcript, not just a
        # cache of the compacted model context. Rewrites update known rows
        # and append new ones, but must not delete raw pre-compaction rows.
        if not messages:
            await self.conn.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
            await self.conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))
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
        await self._rebuild_session_turns(session_id)

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

    def _is_turn_message(self, row: aiosqlite.Row) -> bool:
        if row["role"] == "system":
            return False
        message = json.loads(row["message_json"])
        content = message.get("content", "")
        return not (isinstance(content, str) and content.startswith(SESSION_HANDOFF_MARKER))

    async def _rebuild_session_turns(self, session_id: str) -> None:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM session_messages WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        )
        await self.conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))

        current_start: aiosqlite.Row | None = None
        current_end: aiosqlite.Row | None = None
        turn_index = 0

        async def flush_current() -> None:
            nonlocal current_start, current_end, turn_index
            if current_start is None or current_end is None:
                return
            turn_id = f"{session_id}:{turn_index}"
            await self.conn.execute(
                """
                INSERT INTO session_turns (
                    session_id, turn_id, turn_index, user_message_id,
                    message_start_id, message_end_id, message_start_seq, message_end_seq,
                    started_at, ended_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_id,
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
            if not self._is_turn_message(row):
                continue
            if row["role"] == "user":
                await flush_current()
                current_start = row
            if current_start is not None:
                current_end = row

        await flush_current()

    async def _ensure_session_messages_unlocked(self, session_id: str) -> None:
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

    async def _ensure_session_messages(self, session_id: str) -> None:
        lock = await self._session_write_lock(session_id)
        async with lock:
            await self._ensure_session_messages_unlocked(session_id)

    async def update_progress(self, state: SessionState, messages: list[dict | Any]) -> None:
        """Lightweight mid-run save: rewrite messages + bump last_activity,
        upserting the row so a fresh session's first save lands instead of
        silently no-op'ing. Leaves metadata alone — the final save in the
        chat service re-stamps last_input_tokens."""
        lock = await self._session_write_lock(state.session_id)
        async with lock:
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
                    state.session_type,
                    state.origin_automation_id,
                ),
            )
            await self._mirror_session_messages(state.session_id, serializable)
            await self.conn.commit()

    async def record_chat_run_started(
        self,
        run_id: str,
        session_id: str,
        *,
        metadata: dict | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        metadata = dict(metadata or {})
        client_id = metadata.get("client_id") if isinstance(metadata.get("client_id"), str) else None
        metadata_json = await asyncio.to_thread(lambda: json.dumps(metadata))
        await self.conn.execute(
            """
            INSERT INTO chat_runs (
                run_id, session_id, status, started_at, updated_at, metadata_json, client_id
            )
            VALUES (?, ?, 'pending', ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                session_id = excluded.session_id,
                status = excluded.status,
                updated_at = excluded.updated_at,
                ended_at = NULL,
                stop_reason = NULL,
                metadata_json = excluded.metadata_json,
                client_id = excluded.client_id,
                error_code = NULL,
                error_message = NULL
            """,
            (run_id, session_id, now, now, metadata_json, client_id),
        )
        await self.conn.commit()

    async def prune_expired_chat_idempotency_keys(self, now: datetime | None = None) -> int:
        now_iso = (now or datetime.now(UTC)).isoformat()
        cursor = await self.conn.execute(
            f"""
            DELETE FROM chat_idempotency_keys
            WHERE expires_at IS NOT NULL
              AND expires_at <= ?
              AND status IN ({", ".join("?" for _ in CHAT_IDEMPOTENCY_TERMINAL_STATUSES)})
            """,
            (now_iso, *CHAT_IDEMPOTENCY_TERMINAL_STATUSES),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def claim_chat_idempotency_key(
        self,
        *,
        session_id: str,
        client_id: str,
        request_hash: str,
        status: str = "accepted",
        expires_at: str | None = None,
    ) -> tuple[bool, dict]:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        expires_at = expires_at or (now_dt + timedelta(days=CHAT_IDEMPOTENCY_TTL_DAYS)).isoformat()
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO chat_idempotency_keys (
                session_id, client_id, request_hash, status, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, client_id, request_hash, status, now, now, expires_at),
        )
        await self.conn.commit()
        row = await self.get_chat_idempotency_key(session_id, client_id)
        if row is None:
            raise RuntimeError("chat idempotency claim insert failed")
        return row["request_hash"] == request_hash and row["created_at"] == now, row

    async def get_chat_idempotency_key(self, session_id: str, client_id: str) -> dict | None:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT * FROM chat_idempotency_keys
            WHERE session_id = ? AND client_id = ?
            """,
            (session_id, client_id),
        )
        if not rows:
            return None
        return self._chat_idempotency_payload(rows[0])

    async def update_chat_idempotency_key(
        self,
        *,
        session_id: str,
        client_id: str,
        status: str,
        run_id: str | None = None,
        message_id: str | None = None,
    ) -> dict | None:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(days=CHAT_IDEMPOTENCY_TTL_DAYS)).isoformat() if status in CHAT_IDEMPOTENCY_TERMINAL_STATUSES else None
        await self.conn.execute(
            """
            UPDATE chat_idempotency_keys
            SET status = ?,
                run_id = COALESCE(?, run_id),
                message_id = COALESCE(?, message_id),
                updated_at = ?,
                expires_at = COALESCE(?, expires_at)
            WHERE session_id = ? AND client_id = ?
            """,
            (status, run_id, message_id, now, expires_at, session_id, client_id),
        )
        await self.conn.commit()
        return await self.get_chat_idempotency_key(session_id, client_id)

    async def record_chat_run_status(
        self,
        run_id: str,
        status: str,
        *,
        stop_reason: str | None = None,
        last_seq: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        ended_at = now if status in {"completed", "cancelled", "error", "failed", "interrupted"} else None
        await self.conn.execute(
            """
            UPDATE chat_runs
            SET status = ?,
                stop_reason = ?,
                updated_at = ?,
                ended_at = COALESCE(?, ended_at),
                last_seq = COALESCE(?, last_seq),
                error_code = COALESCE(?, error_code),
                error_message = COALESCE(?, error_message)
            WHERE run_id = ?
            """,
            (status, stop_reason, now, ended_at, last_seq, error_code, error_message, run_id),
        )
        await self.conn.commit()

    async def get_chat_run(self, run_id: str) -> dict | None:
        rows = await self.read_conn.execute_fetchall("SELECT * FROM chat_runs WHERE run_id = ?", (run_id,))
        if not rows:
            return None
        return self._chat_run_payload(rows[0])


    async def get_latest_chat_run_for_session(self, session_id: str) -> dict | None:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT * FROM chat_runs
            WHERE session_id = ?
            ORDER BY updated_at DESC, started_at DESC
            LIMIT 1
            """,
            (session_id,),
        )
        if not rows:
            return None
        return self._chat_run_payload(rows[0])

    async def list_pending_tool_approvals(self, session_id: str, *, run_id: str | None = None) -> list[dict]:
        if run_id is not None:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM tool_approvals
                WHERE session_id = ? AND run_id = ? AND status = 'pending'
                ORDER BY requested_at ASC
                """,
                (session_id, run_id),
            )
        else:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM tool_approvals
                WHERE session_id = ? AND status = 'pending'
                ORDER BY requested_at ASC
                """,
                (session_id,),
            )
        return [self._tool_approval_payload(row) for row in rows]

    async def record_tool_call_started(
        self,
        *,
        run_id: str,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        action: str,
        scope: str,
        args_hash: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            INSERT INTO tool_calls (
                run_id, session_id, tool_call_id, tool_name, action, scope,
                args_hash, status, started_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            ON CONFLICT(run_id, tool_call_id) DO UPDATE SET
                run_id = excluded.run_id,
                session_id = excluded.session_id,
                tool_name = excluded.tool_name,
                action = excluded.action,
                scope = excluded.scope,
                args_hash = excluded.args_hash,
                status = excluded.status,
                result_preview = NULL,
                started_at = excluded.started_at,
                ended_at = NULL
            """,
            (run_id, session_id, tool_call_id, tool_name, action, scope, args_hash, now),
        )
        await self.conn.commit()

    async def record_tool_call_finished(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        status: str,
        result_preview: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            UPDATE tool_calls
            SET status = ?, result_preview = ?, ended_at = ?
            WHERE run_id = ? AND tool_call_id = ?
            """,
            (status, result_preview, now, run_id, tool_call_id),
        )
        await self.conn.commit()

    async def list_tool_calls(self, *, run_id: str) -> list[dict]:
        rows = await self.read_conn.execute_fetchall(
            "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY started_at ASC",
            (run_id,),
        )
        return [self._tool_call_payload(row) for row in rows]

    async def record_tool_approval_requested(
        self,
        *,
        run_id: str,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        action: str,
        scope: str,
        preview: str | None = None,
        diff: str | None = None,
        expires_at: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            INSERT INTO tool_approvals (
                run_id, session_id, tool_call_id, tool_name, action, scope,
                preview, diff, status, requested_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(run_id, tool_call_id) DO UPDATE SET
                session_id = excluded.session_id,
                tool_name = excluded.tool_name,
                action = excluded.action,
                scope = excluded.scope,
                preview = excluded.preview,
                diff = excluded.diff,
                status = excluded.status,
                requested_at = excluded.requested_at,
                resolved_at = NULL,
                expires_at = excluded.expires_at,
                result_feedback = NULL
            """,
            (run_id, session_id, tool_call_id, tool_name, action, scope, preview, diff, now, expires_at),
        )
        await self.conn.commit()

    async def resolve_tool_approval(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        status: str,
        result_feedback: str | None = None,
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        cursor = await self.conn.execute(
            """
            UPDATE tool_approvals
            SET status = ?,
                resolved_at = COALESCE(resolved_at, ?),
                result_feedback = COALESCE(?, result_feedback)
            WHERE run_id = ? AND tool_call_id = ?
              AND status = 'pending'
            """,
            (status, now, result_feedback, run_id, tool_call_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def expire_tool_approval(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        result_feedback: str | None = None,
    ) -> bool:
        return await self.resolve_tool_approval(
            run_id=run_id,
            tool_call_id=tool_call_id,
            status="expired",
            result_feedback=result_feedback,
        )

    async def get_tool_approval(self, *, run_id: str, tool_call_id: str) -> dict | None:
        rows = await self.read_conn.execute_fetchall(
            "SELECT * FROM tool_approvals WHERE run_id = ? AND tool_call_id = ?",
            (run_id, tool_call_id),
        )
        if not rows:
            return None
        return self._tool_approval_payload(rows[0])

    async def mark_interrupted_chat_runs(self) -> int:
        now = datetime.now(UTC).isoformat()
        cursor = await self.conn.execute(
            """
            UPDATE chat_runs
            SET status = 'interrupted',
                stop_reason = 'server_restart',
                error_code = 'run_interrupted',
                error_message = 'Run was interrupted by server restart.',
                updated_at = ?,
                ended_at = ?
            WHERE status IN ('pending', 'running', 'backgrounded')
            """,
            (now, now),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def record_background_agent_started(
        self,
        *,
        task_id: str,
        session_id: str,
        parent_run_id: str | None,
        command: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            INSERT INTO background_agent_runs (
                task_id, session_id, parent_run_id, status, command,
                created_at, started_at, updated_at
            )
            VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
            ON CONFLICT(session_id, task_id) DO UPDATE SET
                session_id = excluded.session_id,
                parent_run_id = excluded.parent_run_id,
                status = 'running',
                command = excluded.command,
                detail = NULL,
                result_ref = NULL,
                result_text = NULL,
                updated_at = excluded.updated_at,
                ended_at = NULL,
                cancel_requested_at = NULL,
                notified_at = NULL
            """,
            (task_id, session_id, parent_run_id, command, now, now, now),
        )
        await self.conn.commit()
        await self.record_background_agent_event(
            task_id=task_id,
            session_id=session_id,
            status="started",
        )

    async def record_background_agent_event(
        self,
        *,
        task_id: str,
        session_id: str,
        status: str,
        detail: str | None = None,
        result_ref: str | None = None,
    ) -> int:
        terminal = status in {"completed", "failed", "cancelled", "interrupted"}
        now = datetime.now(UTC).isoformat()
        async with self._background_event_lock:
            rows = await self.conn.execute_fetchall(
                """
                SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq
                FROM background_agent_events
                WHERE session_id = ?
                """,
                (session_id,),
            )
            seq = int(rows[0]["next_seq"])
            await self.conn.execute(
                """
                INSERT INTO background_agent_events (
                    session_id, seq, task_id, status, detail, result_ref, terminal, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, seq, task_id, status, detail, result_ref, int(terminal), now),
            )
            await self.conn.execute(
                """
            UPDATE background_agent_runs
            SET detail = COALESCE(?, detail),
                result_ref = COALESCE(?, result_ref),
                updated_at = ?
            WHERE session_id = ? AND task_id = ?
            """,
                (detail, result_ref, now, session_id, task_id),
            )
            await self.conn.commit()
        return seq

    async def record_background_agent_finished(
        self,
        *,
        task_id: str,
        session_id: str,
        status: str,
        result_ref: str | None = None,
        detail: str | None = None,
        result_text: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            UPDATE background_agent_runs
            SET status = ?,
                detail = COALESCE(?, detail),
                result_ref = COALESCE(?, result_ref),
                result_text = COALESCE(?, result_text),
                updated_at = ?,
                ended_at = COALESCE(ended_at, ?)
            WHERE session_id = ? AND task_id = ?
            """,
            (status, detail, result_ref, result_text, now, now, session_id, task_id),
        )
        await self.conn.commit()
        await self.record_background_agent_event(
            task_id=task_id,
            session_id=session_id,
            status=status,
            detail=detail,
            result_ref=result_ref,
        )

    async def request_background_agent_cancel(self, session_id: str, task_id: str) -> bool:
        now = datetime.now(UTC).isoformat()
        cursor = await self.conn.execute(
            """
            UPDATE background_agent_runs
            SET status = 'cancel_requested',
                cancel_requested_at = COALESCE(cancel_requested_at, ?),
                updated_at = ?
            WHERE session_id = ? AND task_id = ?
              AND status NOT IN ('completed', 'failed', 'cancelled', 'interrupted')
            """,
            (now, now, session_id, task_id),
        )
        await self.conn.commit()
        changed = cursor.rowcount > 0
        if changed:
            await self.record_background_agent_event(
                task_id=task_id,
                session_id=session_id,
                status="cancel_requested",
            )
        return changed

    async def get_background_agent_result(self, session_id: str, task_id: str) -> str | None:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT result_text FROM background_agent_runs
            WHERE session_id = ? AND task_id = ?
            """,
            (session_id, task_id),
        )
        if not rows:
            return None
        value = rows[0]["result_text"]
        return value if isinstance(value, str) else None

    async def list_background_agent_runs(
        self,
        session_id: str,
        *,
        include_terminal: bool = True,
    ) -> list[dict]:
        if include_terminal:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM background_agent_runs
                WHERE session_id = ?
                ORDER BY updated_at DESC
                """,
                (session_id,),
            )
        else:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM background_agent_runs
                WHERE session_id = ?
                  AND status NOT IN ('completed', 'failed', 'cancelled', 'interrupted')
                ORDER BY updated_at DESC
                """,
                (session_id,),
            )
        return [self._background_agent_payload(row) for row in rows]

    async def list_background_agent_events(
        self,
        session_id: str,
        *,
        after_seq: int = 0,
        limit: int = 10000,
    ) -> list[dict]:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT * FROM background_agent_events
            WHERE session_id = ? AND seq > ?
            ORDER BY seq ASC
            LIMIT ?
            """,
            (session_id, after_seq, limit),
        )
        return [self._background_agent_event_payload(row) for row in rows]

    async def mark_interrupted_background_agent_runs(self) -> int:
        now = datetime.now(UTC).isoformat()
        rows = await self.conn.execute_fetchall(
            """
            SELECT task_id, session_id FROM background_agent_runs
            WHERE status IN ('running', 'activity', 'cancel_requested')
            """,
        )
        if not rows:
            return 0
        await self.conn.execute(
            """
            UPDATE background_agent_runs
            SET status = 'interrupted',
                detail = COALESCE(detail, 'server_restart'),
                updated_at = ?,
                ended_at = COALESCE(ended_at, ?)
            WHERE status IN ('running', 'activity', 'cancel_requested')
            """,
            (now, now),
        )
        for row in rows:
            await self.record_background_agent_event(
                task_id=row["task_id"],
                session_id=row["session_id"],
                status="interrupted",
                detail="server_restart",
            )
        await self.conn.commit()
        return len(rows)

    async def mark_interrupted_chat_queued_messages_retryable(self) -> int:
        now = datetime.now(UTC).isoformat()
        cursor = await self.conn.execute(
            """
            UPDATE chat_queued_messages
            SET status = 'failed_retryable',
                updated_at = ?
            WHERE status = 'queued'
              AND run_id IN (
                SELECT run_id FROM chat_runs WHERE status = 'interrupted'
              )
            """,
            (now,),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def record_chat_queued_message(
        self,
        *,
        client_id: str,
        session_id: str,
        run_id: str,
        message: dict,
        enqueued_seq: int | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        message_json = await asyncio.to_thread(lambda: json.dumps(message, default=str))
        await self.conn.execute(
            """
            INSERT INTO chat_queued_messages (
                client_id, session_id, run_id, status, message_json, enqueued_at, updated_at, enqueued_seq
            )
            VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                session_id = excluded.session_id,
                run_id = excluded.run_id,
                status = excluded.status,
                message_json = excluded.message_json,
                updated_at = excluded.updated_at,
                enqueued_seq = excluded.enqueued_seq,
                ingested_at = NULL,
                ingested_seq = NULL
            """,
            (client_id, session_id, run_id, message_json, now, now, enqueued_seq),
        )
        await self.conn.commit()

    async def mark_chat_queued_message_ingested(self, client_id: str, *, ingested_seq: int | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            UPDATE chat_queued_messages
            SET status = 'ingested', updated_at = ?, ingested_at = ?, ingested_seq = COALESCE(?, ingested_seq)
            WHERE client_id = ?
            """,
            (now, now, ingested_seq, client_id),
        )
        await self.conn.commit()

    async def mark_chat_queued_message_cancelled(self, client_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            UPDATE chat_queued_messages
            SET status = 'cancelled', updated_at = ?
            WHERE client_id = ? AND status = 'queued'
            """,
            (now, client_id),
        )
        await self.conn.commit()

    async def list_chat_queued_messages(self, session_id: str, *, status: str | None = None) -> list[dict]:
        if status:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM chat_queued_messages
                WHERE session_id = ? AND status = ?
                ORDER BY enqueued_at ASC
                """,
                (session_id, status),
            )
        else:
            rows = await self.read_conn.execute_fetchall(
                """
                SELECT * FROM chat_queued_messages
                WHERE session_id = ?
                ORDER BY enqueued_at ASC
                """,
                (session_id,),
            )
        return [self._chat_queued_message_payload(row) for row in rows]

    async def record_session_event(self, record: StreamRecord) -> None:
        sse = record.event.to_sse()
        payload = json.loads(sse["data"])
        event_json = await asyncio.to_thread(lambda: json.dumps(payload, default=str))
        run_id = payload.get("run_id") if isinstance(payload.get("run_id"), str) else None
        await self.conn.execute(
            """
            INSERT INTO session_events (
                session_id, seq, event_type, event_json, run_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.session_id,
                record.seq,
                str(payload.get("type") or sse["event"]),
                event_json,
                run_id,
                datetime.now(UTC).isoformat(),
            ),
        )
        await self.conn.commit()

    async def list_session_events(
        self,
        session_id: str,
        *,
        after_seq: int = 0,
        limit: int = 10000,
    ) -> list[StreamRecord]:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT seq, event_json
            FROM session_events
            WHERE session_id = ? AND seq > ?
            ORDER BY seq ASC
            LIMIT ?
            """,
            (session_id, after_seq, limit),
        )
        records: list[StreamRecord] = []
        for row in rows:
            payload = json.loads(row["event_json"])
            records.append(
                StreamRecord(
                    seq=row["seq"],
                    session_id=session_id,
                    event=event_from_payload(payload),
                )
            )
        return records

    async def get_latest_session_event_seq(self, session_id: str) -> int:
        rows = await self.read_conn.execute_fetchall(
            "SELECT COALESCE(MAX(seq), 0) AS latest_seq FROM session_events WHERE session_id = ?",
            (session_id,),
        )
        return int(rows[0]["latest_seq"] or 0)

    async def get_latest_session_checkpoint_seq(self, session_id: str) -> int:
        rows = await self.read_conn.execute_fetchall(
            "SELECT COALESCE(MAX(last_seq), 0) AS latest_seq FROM chat_runs WHERE session_id = ? AND last_seq IS NOT NULL",
            (session_id,),
        )
        return int(rows[0]["latest_seq"] or 0)

    async def record_chat_compaction(
        self,
        *,
        compaction_id: str,
        session_id: str,
        boundary_seq: int,
        messages_before: int,
        messages_after: int,
        rehydration_state: dict | None = None,
    ) -> None:
        rehydration_state_json = await asyncio.to_thread(
            lambda: json.dumps(rehydration_state, default=str) if rehydration_state is not None else None
        )
        await self.conn.execute(
            """
            INSERT INTO chat_compactions (
                compaction_id, session_id, boundary_seq, messages_before, messages_after,
                rehydration_state, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(compaction_id) DO UPDATE SET
                session_id = excluded.session_id,
                boundary_seq = excluded.boundary_seq,
                messages_before = excluded.messages_before,
                messages_after = excluded.messages_after,
                rehydration_state = excluded.rehydration_state
            """,
            (
                compaction_id,
                session_id,
                boundary_seq,
                messages_before,
                messages_after,
                rehydration_state_json,
                datetime.now(UTC).isoformat(),
            ),
        )
        await self.conn.commit()

    async def list_chat_compactions(self, session_id: str) -> list[dict]:
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT *
            FROM chat_compactions
            WHERE session_id = ?
            ORDER BY boundary_seq ASC
            """,
            (session_id,),
        )
        return [
            {
                "compaction_id": row["compaction_id"],
                "session_id": row["session_id"],
                "boundary_seq": row["boundary_seq"],
                "messages_before": row["messages_before"],
                "messages_after": row["messages_after"],
                "rehydration_state": json.loads(row["rehydration_state"]) if row["rehydration_state"] else None,
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def save_session(self, state: SessionState, messages: list[dict | Any], metadata: dict | None = None) -> None:
        lock = await self._session_write_lock(state.session_id)
        async with lock:
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
                    state.session_type,
                    state.origin_automation_id,
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
            session_type=row["session_type"] or "chat",
            origin_automation_id=row["origin_automation_id"],
        )

        raw_messages, raw_metadata = row["messages"], row["metadata"]
        messages, metadata = await asyncio.to_thread(
            lambda: (json.loads(raw_messages) if raw_messages else [], json.loads(raw_metadata) if raw_metadata else {})
        )
        return SessionData(
            state=state,
            messages=messages,
            last_input_tokens=metadata.get("last_input_tokens"),
            last_message_count=metadata.get("last_message_count"),
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
                "session_type": row["session_type"] or "chat",
                "origin_automation_id": row["origin_automation_id"],
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
                "session_type": row["session_type"] or "chat",
                "origin_automation_id": row["origin_automation_id"],
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
            rows = await self._latest_rows_with_visible_user_anchor(session_id, rows)

        messages = [self._message_row_payload(row) for row in rows]
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

    def _row_is_visible_user(self, row: Any) -> bool:
        if row["role"] != "user":
            return False
        try:
            message = json.loads(row["message_json"])
        except Exception:
            return True
        return not bool(message.get("is_meta"))

    async def _latest_rows_with_visible_user_anchor(self, session_id: str, rows: list[Any]) -> list[Any]:
        if not rows or any(self._row_is_visible_user(row) for row in rows):
            return rows
        first_seq = rows[0]["seq"]
        anchors = await self.read_conn.execute_fetchall(
            """
            SELECT * FROM session_messages
            WHERE session_id = ? AND seq < ? AND role = 'user'
            ORDER BY seq DESC
            LIMIT 1
            """,
            (session_id, first_seq),
        )
        if not anchors:
            return rows
        anchor = anchors[0]
        if not self._row_is_visible_user(anchor):
            return rows
        return await self.read_conn.execute_fetchall(
            """
            SELECT * FROM session_messages
            WHERE session_id = ? AND seq >= ?
            ORDER BY seq ASC
            LIMIT 250
            """,
            (session_id, anchor["seq"]),
        )

    async def delete_session_messages_from(
        self,
        session_id: str,
        message_id: str | None = None,
        seq: int | None = None,
    ) -> bool:
        lock = await self._session_write_lock(session_id)
        async with lock:
            await self._ensure_session_messages_unlocked(session_id)
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
            await self._rebuild_session_turns(session_id)
            await self.conn.commit()
            return cursor.rowcount > 0

    async def list_session_turns(self, session_id: str, limit: int = 100) -> list[dict]:
        await self._ensure_session_messages(session_id)
        rows = await self.read_conn.execute_fetchall(
            """
            SELECT *
            FROM session_turns
            WHERE session_id = ?
            ORDER BY turn_index ASC
            LIMIT ?
            """,
            (session_id, max(1, min(limit, 500))),
        )
        return [
            {
                "session_id": row["session_id"],
                "turn_id": row["turn_id"],
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

    async def list_session_episodes(self, session_id: str, limit: int = 100) -> list[dict]:
        # Compatibility for old API/tool callers. These are transcript turns,
        # not true memory episodes.
        turns = await self.list_session_turns(session_id, limit=limit)
        return [{**turn, "episode_id": turn["turn_id"]} for turn in turns]
