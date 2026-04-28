import json
from datetime import datetime

import aiosqlite

from ntrp.automation.models import Automation
from ntrp.automation.triggers import parse_triggers
from ntrp.logging import get_logger

_logger = get_logger(__name__)


def _parse_dt(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw) if raw else None


def _row_to_automation(row: dict) -> Automation:
    return Automation(
        task_id=row["task_id"],
        name=row["name"],
        description=row["description"],
        model=row["model"],
        triggers=parse_triggers(row["triggers"]),
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        next_run_at=_parse_dt(row["next_run_at"]),
        last_run_at=_parse_dt(row["last_run_at"]),
        last_result=row["last_result"],
        running_since=_parse_dt(row["running_since"]),
        writable=bool(row["writable"]),
        handler=row["handler"],
        builtin=bool(row["builtin"]),
        cooldown_minutes=int(row["cooldown_minutes"]) if row["cooldown_minutes"] is not None else None,
    )


def _serialize_triggers(triggers: list) -> str:
    return json.dumps([{"type": t.type, **t.params()} for t in triggers])


_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    model TEXT,
    triggers TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    next_run_at TEXT,
    notifiers TEXT,
    last_result TEXT,
    running_since TEXT,
    writable INTEGER NOT NULL DEFAULT 0,
    handler TEXT,
    builtin INTEGER NOT NULL DEFAULT 0,
    cooldown_minutes INTEGER
);

CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_next_run ON scheduled_tasks(next_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_enabled ON scheduled_tasks(enabled);

CREATE TABLE IF NOT EXISTS automation_event_dedupe (
    task_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (task_id, event_key)
);

CREATE INDEX IF NOT EXISTS idx_automation_event_dedupe_seen_at
ON automation_event_dedupe(seen_at);

CREATE TABLE IF NOT EXISTS automation_event_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    context TEXT NOT NULL,
    created_at TEXT NOT NULL,
    claimed_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_attempt_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_automation_event_queue_task_claimed_id
ON automation_event_queue(task_id, claimed_at, id);

CREATE TABLE IF NOT EXISTS automation_count_state (
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (task_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_automation_count_state_updated_at
ON automation_count_state(updated_at);

CREATE TABLE IF NOT EXISTS chat_extraction_state (
    session_id TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL DEFAULT 0,
    messages TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    pending INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_extraction_state_pending
ON chat_extraction_state(pending, updated_at);

CREATE TABLE IF NOT EXISTS automation_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_COLUMNS = (
    "task_id, name, description, model, triggers, enabled, "
    "created_at, last_run_at, next_run_at, last_result, running_since, "
    "writable, handler, builtin, cooldown_minutes"
)

_SQL_SAVE = f"""
INSERT OR REPLACE INTO scheduled_tasks ({_COLUMNS})
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SQL_GET_BY_ID = f"SELECT {_COLUMNS} FROM scheduled_tasks WHERE task_id = ?"

_SQL_LIST_ALL = f"SELECT {_COLUMNS} FROM scheduled_tasks ORDER BY created_at"

_SQL_LIST_DUE = f"""
SELECT {_COLUMNS} FROM scheduled_tasks
WHERE enabled = 1 AND next_run_at <= ? AND running_since IS NULL
ORDER BY next_run_at
"""

_SQL_LIST_EVENT_TRIGGERED = f"""
SELECT {_COLUMNS} FROM scheduled_tasks
WHERE enabled = 1
  AND EXISTS (
    SELECT 1 FROM json_each(triggers)
    WHERE json_extract(value, '$.type') = 'event'
      AND json_extract(value, '$.event_type') = ?
  )
"""

_SQL_LIST_BY_TRIGGER_TYPE = f"""
SELECT {_COLUMNS} FROM scheduled_tasks
WHERE enabled = 1
  AND running_since IS NULL
  AND EXISTS (
    SELECT 1 FROM json_each(triggers)
    WHERE json_extract(value, '$.type') = ?
  )
"""

_SQL_UPDATE_LAST_RUN = """
UPDATE scheduled_tasks
SET last_run_at = ?, next_run_at = ?, last_result = ?
WHERE task_id = ?
"""

_SQL_SET_NEXT_RUN = """
UPDATE scheduled_tasks SET next_run_at = ? WHERE task_id = ?
"""

_SQL_TRY_MARK_RUNNING = """
UPDATE scheduled_tasks
SET running_since = ?
WHERE task_id = ?
  AND enabled = 1
  AND running_since IS NULL
"""

_SQL_CLEAR_RUNNING = "UPDATE scheduled_tasks SET running_since = NULL WHERE task_id = ?"

_SQL_DELETE = "DELETE FROM scheduled_tasks WHERE task_id = ?"

_SQL_SET_ENABLED = "UPDATE scheduled_tasks SET enabled = ? WHERE task_id = ?"

_SQL_SET_WRITABLE = "UPDATE scheduled_tasks SET writable = ? WHERE task_id = ?"

_SQL_UPDATE_METADATA = """
UPDATE scheduled_tasks
SET name = ?, description = ?, model = ?, triggers = ?,
    enabled = ?, next_run_at = ?, writable = ?,
    cooldown_minutes = ?
WHERE task_id = ?
"""

_SQL_CLEAR_ALL_RUNNING = "UPDATE scheduled_tasks SET running_since = NULL WHERE running_since IS NOT NULL"

_SQL_UPDATE_NAME = "UPDATE scheduled_tasks SET name = ? WHERE task_id = ?"

_SQL_UPDATE_DESCRIPTION = "UPDATE scheduled_tasks SET description = ? WHERE task_id = ?"

_SQL_CLAIM_EVENT = """
INSERT OR IGNORE INTO automation_event_dedupe (task_id, event_key, seen_at)
VALUES (?, ?, ?)
"""

_SQL_EVICT_EVENT_CLAIMS = "DELETE FROM automation_event_dedupe WHERE seen_at < ?"

_SQL_ENQUEUE_EVENT = """
INSERT INTO automation_event_queue (task_id, event_key, context, created_at)
VALUES (?, ?, ?, ?)
"""

_SQL_LIST_TASKS_WITH_PENDING_EVENTS = """
SELECT DISTINCT task_id
FROM automation_event_queue
WHERE claimed_at IS NULL
"""

_SQL_CLAIM_NEXT_EVENT_CANDIDATE = """
SELECT id, context, attempt_count
FROM automation_event_queue
WHERE task_id = ?
  AND claimed_at IS NULL
  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
ORDER BY id
LIMIT 1
"""

_SQL_CLAIM_EVENT_QUEUE_ROW = """
UPDATE automation_event_queue
SET claimed_at = ?
WHERE id = ? AND claimed_at IS NULL
"""

_SQL_COMPLETE_EVENT = "DELETE FROM automation_event_queue WHERE id = ?"

_SQL_FAIL_EVENT = """
UPDATE automation_event_queue
SET claimed_at = NULL,
    attempt_count = attempt_count + 1,
    last_error = ?,
    next_attempt_at = ?
WHERE id = ?
"""

_SQL_DELETE_DEDUPE_BY_TASK = "DELETE FROM automation_event_dedupe WHERE task_id = ?"

_SQL_DELETE_QUEUE_BY_TASK = "DELETE FROM automation_event_queue WHERE task_id = ?"

_SQL_RELEASE_ALL_CLAIMED_EVENTS = "UPDATE automation_event_queue SET claimed_at = NULL WHERE claimed_at IS NOT NULL"

_SQL_INCREMENT_COUNT = """
INSERT INTO automation_count_state (task_id, session_id, count, updated_at)
VALUES (?, ?, 1, ?)
ON CONFLICT(task_id, session_id) DO UPDATE SET
    count = count + 1,
    updated_at = excluded.updated_at
"""

_SQL_GET_COUNT = "SELECT count FROM automation_count_state WHERE task_id = ? AND session_id = ?"

_SQL_CLEAR_COUNT = "DELETE FROM automation_count_state WHERE task_id = ? AND session_id = ?"

_SQL_DELETE_COUNTS_BY_TASK = "DELETE FROM automation_count_state WHERE task_id = ?"

_SQL_RECORD_CHAT_EXTRACTION_ACTIVITY = """
INSERT INTO chat_extraction_state (session_id, cursor, messages, message_count, pending, updated_at)
VALUES (?, 0, ?, ?, 1, ?)
ON CONFLICT(session_id) DO UPDATE SET
    cursor = CASE
        WHEN chat_extraction_state.cursor > excluded.message_count THEN excluded.message_count
        ELSE chat_extraction_state.cursor
    END,
    messages = excluded.messages,
    message_count = excluded.message_count,
    pending = CASE
        WHEN (
            CASE
                WHEN chat_extraction_state.cursor > excluded.message_count THEN excluded.message_count
                ELSE chat_extraction_state.cursor
            END
        ) < excluded.message_count THEN 1
        ELSE 0
    END,
    updated_at = excluded.updated_at
"""

_SQL_LIST_PENDING_CHAT_EXTRACTION = """
SELECT session_id, cursor, messages, message_count
FROM chat_extraction_state
WHERE pending = 1
ORDER BY updated_at
LIMIT ?
"""

_SQL_GET_CHAT_EXTRACTION_CURSOR = "SELECT cursor FROM chat_extraction_state WHERE session_id = ?"

_SQL_MARK_CHAT_EXTRACTION_EXTRACTED = """
UPDATE chat_extraction_state
SET cursor = ?,
    pending = CASE WHEN message_count > ? THEN 1 ELSE 0 END,
    updated_at = ?
WHERE session_id = ?
"""


# --- Migration ---

_MIGRATION_V1 = """
CREATE TABLE IF NOT EXISTS automation_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE scheduled_tasks_new (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    model TEXT,
    triggers TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    next_run_at TEXT,
    notifiers TEXT,
    last_result TEXT,
    running_since TEXT,
    writable INTEGER NOT NULL DEFAULT 0,
    handler TEXT,
    builtin INTEGER NOT NULL DEFAULT 0,
    cooldown_minutes INTEGER
);

INSERT INTO scheduled_tasks_new (
    task_id, name, description, model, triggers, enabled,
    created_at, last_run_at, next_run_at, notifiers, last_result, running_since,
    writable, handler, builtin, cooldown_minutes
)
SELECT
    task_id, name, description, model, json_array(json(trigger)), enabled,
    created_at, last_run_at, next_run_at, notifiers, last_result, running_since,
    writable, NULL, 0, NULL
FROM scheduled_tasks;

DROP TABLE scheduled_tasks;
ALTER TABLE scheduled_tasks_new RENAME TO scheduled_tasks;

CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_next_run ON scheduled_tasks(next_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_enabled ON scheduled_tasks(enabled);
"""

CURRENT_SCHEMA_VERSION = 2

_DAY_INT_TO_NAME = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


def _normalize_trigger(t: dict) -> dict:
    """Convert any legacy trigger format to the canonical string-based format.

    Handles:
    - asdict() dicts: {"hour":16,"minute":0}, {"days":[0,1,2,...]}, {"delta":{"seconds":...}}
    - Pre-v1 keys: "time_of_day"/"recurrence"/"repeat"
    - Stray null values from old params() serialization
    """
    typ = t.get("type", "time")

    if typ == "time":
        # Pre-v1 legacy: time_of_day / recurrence / repeat
        if "time_of_day" in t:
            at = t["time_of_day"]
            recurrence = t.get("recurrence") or t.get("repeat", "once")
            out = {"type": "time", "at": at}
            if recurrence != "once":
                out["days"] = recurrence
            return out

        out: dict = {"type": "time"}
        for key in ("at", "start", "end"):
            val = t.get(key)
            if isinstance(val, dict) and "hour" in val:
                out[key] = f"{val['hour']:02d}:{val['minute']:02d}"
            elif isinstance(val, str):
                out[key] = val

        val = t.get("days")
        if isinstance(val, dict) and "days" in val:
            days = sorted(val["days"])
            if days == list(range(7)):
                out["days"] = "daily"
            elif days == list(range(5)):
                out["days"] = "weekdays"
            else:
                out["days"] = ",".join(_DAY_INT_TO_NAME[d] for d in days)
        elif isinstance(val, str):
            out["days"] = val

        val = t.get("every")
        if isinstance(val, dict) and "delta" in val:
            td = val["delta"]
            secs = int(td.get("seconds", 0)) + int(td.get("hours", 0)) * 3600 + int(td.get("minutes", 0)) * 60
            h, m = divmod(secs // 60, 60)
            out["every"] = f"{h}h{m}m" if h and m else (f"{h}h" if h else f"{m}m")
        elif isinstance(val, str):
            out["every"] = val

        return out

    if typ == "event":
        out = {"type": "event", "event_type": t["event_type"]}
        if t.get("lead_minutes") is not None:
            out["lead_minutes"] = t["lead_minutes"]
        return out

    if typ == "idle":
        return {"type": "idle", "idle_minutes": t["idle_minutes"]}

    if typ == "count":
        return {"type": "count", "every_n": t["every_n"]}

    return t


async def _migrate_v2(conn: aiosqlite.Connection) -> None:
    rows = await conn.execute_fetchall("SELECT task_id, triggers FROM scheduled_tasks")
    for row in rows:
        items = json.loads(row["triggers"])
        normalized = [_normalize_trigger(t) for t in items]
        new_json = json.dumps(normalized)
        if new_json != row["triggers"]:
            await conn.execute(
                "UPDATE scheduled_tasks SET triggers = ? WHERE task_id = ?",
                (new_json, row["task_id"]),
            )
    _logger.info("Migrated triggers to v2 (canonical string format)")


async def _get_schema_version(conn: aiosqlite.Connection) -> int:
    try:
        rows = await conn.execute_fetchall("SELECT value FROM automation_meta WHERE key = 'schema_version'")
        if rows:
            return int(rows[0]["value"])
    except Exception:
        pass
    return 0


async def _set_schema_version(conn: aiosqlite.Connection, version: int) -> None:
    await conn.execute(
        "INSERT OR REPLACE INTO automation_meta (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


async def _migrate(conn: aiosqlite.Connection) -> None:
    version = await _get_schema_version(conn)

    if version < 1:
        # Check if old schema exists (has 'trigger' column instead of 'triggers')
        try:
            rows = await conn.execute_fetchall("PRAGMA table_info(scheduled_tasks)")
            columns = {row["name"] for row in rows}
            if "trigger" in columns and "triggers" not in columns:
                _logger.info("Migrating automation store to v1 (trigger -> triggers)")
                await conn.executescript(_MIGRATION_V1)
                await _set_schema_version(conn, 1)
                await conn.commit()
            elif "triggers" in columns:
                # Already on new schema, just ensure meta table and version
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS automation_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                await _set_schema_version(conn, 1)
                await conn.commit()
            else:
                pass
        except Exception:
            pass

    if version < 2:
        try:
            await _migrate_v2(conn)
            await _set_schema_version(conn, 2)
            await conn.commit()
        except Exception:
            pass


class AutomationStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def init_schema(self) -> None:
        await _migrate(self.conn)
        await self.conn.executescript(_SCHEMA)
        await _set_schema_version(self.conn, CURRENT_SCHEMA_VERSION)
        await self.conn.commit()

    async def save(self, automation: Automation) -> None:
        await self.conn.execute(
            _SQL_SAVE,
            (
                automation.task_id,
                automation.name,
                automation.description,
                automation.model,
                _serialize_triggers(automation.triggers),
                int(automation.enabled),
                automation.created_at.isoformat(),
                automation.last_run_at.isoformat() if automation.last_run_at else None,
                automation.next_run_at.isoformat() if automation.next_run_at else None,
                automation.last_result,
                automation.running_since.isoformat() if automation.running_since else None,
                int(automation.writable),
                automation.handler,
                int(automation.builtin),
                automation.cooldown_minutes,
            ),
        )
        await self.conn.commit()

    async def get(self, task_id: str) -> Automation | None:
        rows = await self.conn.execute_fetchall(_SQL_GET_BY_ID, (task_id,))
        if not rows:
            return None
        return _row_to_automation(rows[0])

    async def list_all(self) -> list[Automation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_ALL)
        return [_row_to_automation(row) for row in rows]

    async def list_due(self, now: datetime) -> list[Automation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_DUE, (now.isoformat(),))
        return [_row_to_automation(row) for row in rows]

    async def list_event_triggered(self, event_type: str) -> list[Automation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_EVENT_TRIGGERED, (event_type,))
        return [_row_to_automation(row) for row in rows]

    async def list_by_trigger_type(self, trigger_type: str) -> list[Automation]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_BY_TRIGGER_TYPE, (trigger_type,))
        return [_row_to_automation(row) for row in rows]

    async def try_mark_running(self, task_id: str, now: datetime) -> bool:
        cursor = await self.conn.execute(_SQL_TRY_MARK_RUNNING, (now.isoformat(), task_id))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def clear_running(self, task_id: str) -> None:
        await self.conn.execute(_SQL_CLEAR_RUNNING, (task_id,))
        await self.conn.commit()

    async def update_last_run(
        self, task_id: str, last_run: datetime, next_run: datetime | None, result: str | None = None
    ) -> None:
        await self.conn.execute(
            _SQL_UPDATE_LAST_RUN,
            (last_run.isoformat(), next_run.isoformat() if next_run else None, result, task_id),
        )
        await self.conn.commit()

    async def delete(self, task_id: str) -> bool:
        cursor = await self.conn.execute(_SQL_DELETE, (task_id,))
        await self.conn.execute(_SQL_DELETE_DEDUPE_BY_TASK, (task_id,))
        await self.conn.execute(_SQL_DELETE_QUEUE_BY_TASK, (task_id,))
        await self.conn.execute(_SQL_DELETE_COUNTS_BY_TASK, (task_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def set_enabled(self, task_id: str, enabled: bool) -> None:
        await self.conn.execute(_SQL_SET_ENABLED, (int(enabled), task_id))
        await self.conn.commit()

    async def set_writable(self, task_id: str, writable: bool) -> None:
        await self.conn.execute(_SQL_SET_WRITABLE, (int(writable), task_id))
        await self.conn.commit()

    async def update_metadata(self, automation: Automation) -> None:
        await self.conn.execute(
            _SQL_UPDATE_METADATA,
            (
                automation.name,
                automation.description,
                automation.model,
                _serialize_triggers(automation.triggers),
                int(automation.enabled),
                automation.next_run_at.isoformat() if automation.next_run_at else None,
                int(automation.writable),
                automation.cooldown_minutes,
                automation.task_id,
            ),
        )
        await self.conn.commit()

    async def clear_all_running(self) -> int:
        cursor = await self.conn.execute(_SQL_CLEAR_ALL_RUNNING)
        await self.conn.commit()
        return cursor.rowcount

    async def set_next_run(self, task_id: str, next_run: datetime) -> None:
        await self.conn.execute(_SQL_SET_NEXT_RUN, (next_run.isoformat(), task_id))
        await self.conn.commit()

    async def update_name(self, task_id: str, name: str) -> None:
        await self.conn.execute(_SQL_UPDATE_NAME, (name, task_id))
        await self.conn.commit()

    async def update_description(self, task_id: str, description: str) -> None:
        await self.conn.execute(_SQL_UPDATE_DESCRIPTION, (description, task_id))
        await self.conn.commit()

    async def claim_event(self, task_id: str, event_key: str, seen_at: datetime) -> bool:
        cursor = await self.conn.execute(_SQL_CLAIM_EVENT, (task_id, event_key, seen_at.isoformat()))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def evict_event_claims_older_than(self, cutoff: datetime) -> None:
        await self.conn.execute(_SQL_EVICT_EVENT_CLAIMS, (cutoff.isoformat(),))
        await self.conn.commit()

    async def enqueue_event(self, task_id: str, event_key: str, context: str, created_at: datetime) -> None:
        await self.conn.execute(
            _SQL_ENQUEUE_EVENT,
            (task_id, event_key, context, created_at.isoformat()),
        )
        await self.conn.commit()

    async def list_tasks_with_pending_events(self) -> list[str]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_TASKS_WITH_PENDING_EVENTS)
        return [row["task_id"] for row in rows]

    async def claim_next_event(self, task_id: str, claimed_at: datetime) -> tuple[int, str, int] | None:
        while True:
            rows = await self.conn.execute_fetchall(
                _SQL_CLAIM_NEXT_EVENT_CANDIDATE,
                (task_id, claimed_at.isoformat()),
            )
            if not rows:
                return None

            queue_id = int(rows[0]["id"])
            context = rows[0]["context"]
            attempt_count = int(rows[0]["attempt_count"] or 0)
            cursor = await self.conn.execute(
                _SQL_CLAIM_EVENT_QUEUE_ROW,
                (claimed_at.isoformat(), queue_id),
            )
            await self.conn.commit()
            if cursor.rowcount > 0:
                return queue_id, context, attempt_count

    async def complete_event(self, queue_id: int) -> None:
        await self.conn.execute(_SQL_COMPLETE_EVENT, (queue_id,))
        await self.conn.commit()

    async def fail_event(self, queue_id: int, error: str, next_attempt_at: datetime) -> None:
        await self.conn.execute(
            _SQL_FAIL_EVENT,
            (error, next_attempt_at.isoformat(), queue_id),
        )
        await self.conn.commit()

    async def release_all_claimed_events(self) -> int:
        cursor = await self.conn.execute(_SQL_RELEASE_ALL_CLAIMED_EVENTS)
        await self.conn.commit()
        return cursor.rowcount

    async def increment_count(self, task_id: str, session_id: str, updated_at: datetime) -> int:
        await self.conn.execute(_SQL_INCREMENT_COUNT, (task_id, session_id, updated_at.isoformat()))
        rows = await self.conn.execute_fetchall(_SQL_GET_COUNT, (task_id, session_id))
        await self.conn.commit()
        return int(rows[0]["count"])

    async def clear_count(self, task_id: str, session_id: str) -> None:
        await self.conn.execute(_SQL_CLEAR_COUNT, (task_id, session_id))
        await self.conn.commit()

    async def record_chat_extraction_activity(
        self,
        session_id: str,
        messages: tuple[dict, ...],
        updated_at: datetime,
    ) -> None:
        await self.conn.execute(
            _SQL_RECORD_CHAT_EXTRACTION_ACTIVITY,
            (
                session_id,
                json.dumps(list(messages), default=str),
                len(messages),
                updated_at.isoformat(),
            ),
        )
        await self.conn.commit()

    async def list_pending_chat_extractions(self, limit: int = 100) -> list[tuple[str, int, tuple[dict, ...]]]:
        rows = await self.conn.execute_fetchall(_SQL_LIST_PENDING_CHAT_EXTRACTION, (limit,))
        return [
            (
                row["session_id"],
                int(row["cursor"]),
                tuple(json.loads(row["messages"])),
            )
            for row in rows
        ]

    async def get_chat_extraction_cursor(self, session_id: str) -> int:
        rows = await self.conn.execute_fetchall(_SQL_GET_CHAT_EXTRACTION_CURSOR, (session_id,))
        return int(rows[0]["cursor"]) if rows else 0

    async def mark_chat_extraction_extracted(self, session_id: str, cursor: int, updated_at: datetime) -> None:
        await self.conn.execute(
            _SQL_MARK_CHAT_EXTRACTION_EXTRACTED,
            (cursor, cursor, updated_at.isoformat(), session_id),
        )
        await self.conn.commit()
