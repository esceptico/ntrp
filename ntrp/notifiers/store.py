import json

import aiosqlite

from ntrp.notifiers.models import NotifierConfig

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifier_configs (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    config TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class NotifierStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def list_all(self) -> list[NotifierConfig]:
        rows = await self.conn.execute_fetchall(
            "SELECT name, type, config, created_at FROM notifier_configs ORDER BY created_at"
        )
        return [NotifierConfig(**row) for row in rows]

    async def get(self, name: str) -> NotifierConfig | None:
        rows = await self.conn.execute_fetchall(
            "SELECT name, type, config, created_at FROM notifier_configs WHERE name = ?",
            (name,),
        )
        if not rows:
            return None
        return NotifierConfig(**rows[0])

    async def save(self, config: NotifierConfig) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO notifier_configs (name, type, config, created_at) VALUES (?, ?, ?, ?)",
            (config.name, config.type, json.dumps(config.config), config.created_at.isoformat()),
        )
        await self.conn.commit()

    async def delete(self, name: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM notifier_configs WHERE name = ?", (name,))
        await self.conn.commit()
        return cursor.rowcount > 0
