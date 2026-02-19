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
            "INSERT INTO notification_log (task_id, subject, body, notifiers, sent_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, subject, body, json.dumps(notifier_names), datetime.now(UTC).isoformat()),
        )
        await self.conn.commit()

    async def recent(self, limit: int = 20, task_id: str | None = None) -> list[NotificationLogEntry]:
        if task_id:
            rows = await self.conn.execute_fetchall(
                "SELECT task_id, subject, body, notifiers, sent_at FROM notification_log "
                "WHERE task_id = ? ORDER BY sent_at DESC LIMIT ?",
                (task_id, limit),
            )
        else:
            rows = await self.conn.execute_fetchall(
                "SELECT task_id, subject, body, notifiers, sent_at FROM notification_log ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            )
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
