"""Remove the demo dataset seeded by ``seed_memory_demo.py`` from the live DB.

Deletes every item tagged ``demo`` (observations/claims/episodes/entities — their
edges cascade) plus the materialized ``northwind-engineers`` directory and its
lens file. Other lenses (e.g. user-authored ones) are left untouched.

Run:  uv run python scripts/clean_memory_demo.py
"""

from __future__ import annotations

import asyncio

import ntrp.database as database
from ntrp.config import get_config
from ntrp.memory.store.base import GraphDatabase

DEMO_TAG = "demo"
DEMO_LENS_SLUG = "northwind-engineers"


async def main() -> None:
    config = get_config()
    conn = await database.connect(config.memory_db_path, vec=True)
    await conn.execute("PRAGMA foreign_keys=ON")
    GraphDatabase(conn, 1536)  # ensure vec extension is loaded

    demo_rows = await conn.execute_fetchall(
        "SELECT id FROM memory_items WHERE tags LIKE ?", (f'%"{DEMO_TAG}"%',)
    )
    for row in demo_rows:
        await conn.execute("DELETE FROM memory_items WHERE id = ?", (row["id"],))

    dir_rows = await conn.execute_fetchall(
        "SELECT id FROM memory_items WHERE kind = 'directory' AND tags LIKE ?",
        (f'%"lens:{DEMO_LENS_SLUG}"%',),
    )
    for row in dir_rows:
        await conn.execute("DELETE FROM memory_items WHERE id = ?", (row["id"],))

    await conn.commit()
    await conn.close()

    lens_path = config.memory_db_path.parent / "memory" / "lenses" / f"{DEMO_LENS_SLUG}.md"
    lens_removed = lens_path.exists()
    lens_path.unlink(missing_ok=True)

    print(f"deleted {len(demo_rows)} demo-tagged item(s)")
    print(f"deleted {len(dir_rows)} demo directory node(s)")
    print(f"removed lens file: {lens_removed} ({lens_path})")


if __name__ == "__main__":
    asyncio.run(main())
