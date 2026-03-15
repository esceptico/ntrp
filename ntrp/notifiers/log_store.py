import json
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    notifiers TEXT NOT NULL,
    sent_at TEXT NOT NULL
);
"""

_COLUMNS = "task_id, subject, body, notifiers, sent_at"
SQL_SAVE = f"INSERT INTO notification_log ({_COLUMNS}) VALUES (?, ?, ?, ?, ?)"
SQL_RECENT = f"SELECT {_COLUMNS} FROM notification_log ORDER BY sent_at DESC LIMIT ?"
SQL_RECENT_BY_TASK = f"SELECT {_COLUMNS} FROM notification_log WHERE task_id = ? ORDER BY sent_at DESC LIMIT ?"


@dataclass
class NotificationLogEntry:
    task_id: str
    subject: str
    body: str
    notifiers: list[str]
    sent_at: datetime


class NotificationLogStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def save(self, task_id: str, subject: str, body: str, notifier_names: list[str]) -> None:
        await self.conn.execute(
            SQL_SAVE, (task_id, subject, body, json.dumps(notifier_names), datetime.now(UTC).isoformat())
        )
        await self.conn.commit()

    async def recent(self, limit: int = 20, task_id: str | None = None) -> list[NotificationLogEntry]:
        if task_id:
            rows = await self.conn.execute_fetchall(SQL_RECENT_BY_TASK, (task_id, limit))
        else:
            rows = await self.conn.execute_fetchall(SQL_RECENT, (limit,))
        return [
            NotificationLogEntry(
                task_id=row["task_id"],
                subject=row["subject"],
                body=row["body"],
                notifiers=json.loads(row["notifiers"]),
                sent_at=datetime.fromisoformat(row["sent_at"]),
            )
            for row in rows
        ]
