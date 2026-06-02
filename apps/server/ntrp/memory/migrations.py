"""Schema-version migration ladder for the memory store.

Greenfield at v1: base DDL lives in store.SCHEMA and is created idempotently
before this runs. New columns/indexes introduced by a future version belong in
that version's migrate fn, not in SCHEMA, so they only run on the upgrade path.
"""

import aiosqlite

from ntrp.logging import get_logger

_logger = get_logger(__name__)

CURRENT_SCHEMA_VERSION = 5


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


async def _migrate_v2(_conn: aiosqlite.Connection) -> None:
    # Historical: added lenses.render_mode. The `lenses` definition table no longer
    # exists (lens definitions are files on disk), so this is now a no-op for any
    # store created at v3+. Kept only to preserve the version ladder.
    pass


async def _migrate_v3(conn: aiosqlite.Connection) -> None:
    # Lens definitions moved from the `lenses` DB table to editable markdown files
    # on disk. Drop the obsolete definition table + its FTS index/triggers; the
    # page cache + membership cache (derived, slug-keyed) stay. No claim is touched.
    await conn.executescript(
        """
        DROP TRIGGER IF EXISTS lenses_ai;
        DROP TRIGGER IF EXISTS lenses_ad;
        DROP TRIGGER IF EXISTS lenses_au;
        DROP TABLE IF EXISTS lenses_fts;
        DROP TABLE IF EXISTS lenses;
        DROP INDEX IF EXISTS idx_lenses_scope;
        """
    )


async def _migrate_v4(conn: aiosqlite.Connection) -> None:
    # Purge the derived lens caches. After the move to file-based lenses (v3), the
    # caches still held STALE rows: orphan entries keyed by the old registry-row
    # UUIDs, plus verdicts/pages computed under earlier (buggy) criteria. These are
    # pure derived data ("drop it and nothing breaks except latency"), so clearing
    # them forces every lens to re-score + re-synthesize fresh against the current
    # file definitions + claims on next view. No claim is touched.
    await conn.executescript(
        """
        DELETE FROM lens_membership_cache;
        DELETE FROM lens_page_cache;
        """
    )


async def _migrate_v5(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lens_inclusion (
            lens_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (lens_id, claim_id)
        );
        """
    )


_MIGRATIONS = (
    (1, _migrate_v1),
    (2, _migrate_v2),
    (3, _migrate_v3),
    (4, _migrate_v4),
    (5, _migrate_v5),
)


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
