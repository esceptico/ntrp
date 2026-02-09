import json
from datetime import datetime

import aiosqlite

from ntrp.schedule.models import ScheduledTask

SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    task_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    recurrence TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    next_run_at TEXT,
    notifiers TEXT,
    last_result TEXT,
    running_since TEXT,
    writable INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_scheduled_next_run ON scheduled_tasks(next_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_enabled ON scheduled_tasks(enabled);
"""

SQL_SAVE = """
INSERT OR REPLACE INTO scheduled_tasks
    (task_id, description, time_of_day, recurrence, enabled,
     created_at, last_run_at, next_run_at, notifiers, last_result, running_since, writable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SQL_LIST_DUE = """
SELECT * FROM scheduled_tasks
WHERE enabled = 1 AND next_run_at <= ? AND running_since IS NULL
ORDER BY next_run_at
"""

SQL_UPDATE_LAST_RUN = """
UPDATE scheduled_tasks
SET last_run_at = ?, next_run_at = ?, last_result = ?
WHERE task_id = ?
"""


class ScheduleStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def save(self, task: ScheduledTask) -> None:
        await self.conn.execute(
            SQL_SAVE,
            (
                task.task_id,
                task.description,
                task.time_of_day,
                task.recurrence.value,
                int(task.enabled),
                task.created_at.isoformat(),
                task.last_run_at.isoformat() if task.last_run_at else None,
                task.next_run_at.isoformat(),
                json.dumps(task.notifiers),
                task.last_result,
                task.running_since.isoformat() if task.running_since else None,
                int(task.writable),
            ),
        )
        await self.conn.commit()

    async def get(self, task_id: str) -> ScheduledTask | None:
        rows = await self.conn.execute_fetchall("SELECT * FROM scheduled_tasks WHERE task_id = ?", (task_id,))
        if not rows:
            return None
        return ScheduledTask(**rows[0])

    async def list_all(self) -> list[ScheduledTask]:
        rows = await self.conn.execute_fetchall("SELECT * FROM scheduled_tasks ORDER BY created_at")
        return [ScheduledTask(**row) for row in rows]

    async def list_due(self, now: datetime) -> list[ScheduledTask]:
        rows = await self.conn.execute_fetchall(SQL_LIST_DUE, (now.isoformat(),))
        return [ScheduledTask(**row) for row in rows]

    async def mark_running(self, task_id: str, now: datetime) -> None:
        await self.conn.execute(
            "UPDATE scheduled_tasks SET running_since = ? WHERE task_id = ?",
            (now.isoformat(), task_id),
        )
        await self.conn.commit()

    async def clear_running(self, task_id: str) -> None:
        await self.conn.execute(
            "UPDATE scheduled_tasks SET running_since = NULL WHERE task_id = ?",
            (task_id,),
        )
        await self.conn.commit()

    async def update_last_run(
        self, task_id: str, last_run: datetime, next_run: datetime, result: str | None = None
    ) -> None:
        await self.conn.execute(
            SQL_UPDATE_LAST_RUN,
            (last_run.isoformat(), next_run.isoformat(), result, task_id),
        )
        await self.conn.commit()

    async def delete(self, task_id: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM scheduled_tasks WHERE task_id = ?", (task_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def set_enabled(self, task_id: str, enabled: bool) -> None:
        await self.conn.execute(
            "UPDATE scheduled_tasks SET enabled = ? WHERE task_id = ?",
            (int(enabled), task_id),
        )
        await self.conn.commit()

    async def set_writable(self, task_id: str, writable: bool) -> None:
        await self.conn.execute(
            "UPDATE scheduled_tasks SET writable = ? WHERE task_id = ?",
            (int(writable), task_id),
        )
        await self.conn.commit()

    async def update_description(self, task_id: str, description: str) -> None:
        await self.conn.execute(
            "UPDATE scheduled_tasks SET description = ? WHERE task_id = ?",
            (description, task_id),
        )
        await self.conn.commit()
