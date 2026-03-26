import json
from dataclasses import asdict
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
    return json.dumps([asdict(t) for t in triggers])


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

CURRENT_SCHEMA_VERSION = 1


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
                # No scheduled_tasks table yet — fresh install, schema will be created
                pass
        except Exception:
            # Table doesn't exist yet
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
