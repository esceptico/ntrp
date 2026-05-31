"""Schema-version migration ladder for the memory store.

Greenfield at v1: base DDL lives in store.SCHEMA and is created idempotently
before this runs. New columns/indexes introduced by a future version belong in
that version's migrate fn, not in SCHEMA, so they only run on the upgrade path.
"""

import aiosqlite

from ntrp.logging import get_logger

_logger = get_logger(__name__)

CURRENT_SCHEMA_VERSION = 1


async def _get_schema_version(conn: aiosqlite.Connection) -> int:
    try:
        rows = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
        return int(rows[0]["value"]) if rows else 0
    except Exception:
        return 0


async def _set_schema_version(conn: aiosqlite.Connection, version: int) -> None:
    await conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


async def _migrate_v1(_conn: aiosqlite.Connection) -> None:
    # Base schema in store.SCHEMA already establishes v1; nothing to migrate.
    pass


_MIGRATIONS = ((1, _migrate_v1),)


async def run_migrations(conn: aiosqlite.Connection) -> None:
    version = await _get_schema_version(conn)
    if version >= CURRENT_SCHEMA_VERSION:
        return
    for target_version, migrate in _MIGRATIONS:
        if version >= target_version:
            continue
        _logger.info("Running memory schema migration v%d", target_version)
        await migrate(conn)
        await _set_schema_version(conn, target_version)
        version = target_version
