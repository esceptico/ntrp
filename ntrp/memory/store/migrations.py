import json

import aiosqlite

from ntrp.logging import get_logger

_logger = get_logger(__name__)

CURRENT_VERSION = 4


async def _get_version(conn: aiosqlite.Connection) -> int:
    try:
        rows = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


async def _set_version(conn: aiosqlite.Connection, version: int) -> None:
    await conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


async def _migrate_v1(conn: aiosqlite.Connection) -> None:
    """Enable foreign keys + recreate entity_refs with ON DELETE CASCADE."""
    _logger.info("Migration v1: adding ON DELETE CASCADE to entity_refs")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_refs_new (
            id INTEGER PRIMARY KEY,
            fact_id INTEGER REFERENCES facts(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL
        )
    """)
    await conn.execute("INSERT INTO entity_refs_new SELECT * FROM entity_refs")
    await conn.execute("DROP TABLE entity_refs")
    await conn.execute("ALTER TABLE entity_refs_new RENAME TO entity_refs")

    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_refs_fact ON entity_refs(fact_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_refs_name ON entity_refs(name)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_refs_entity ON entity_refs(entity_id)")


async def _migrate_v2(conn: aiosqlite.Connection) -> None:
    """Drop evidence_count column (redundant with len(source_fact_ids))."""
    _logger.info("Migration v2: dropping evidence_count from observations")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS observations_new (
            id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL,
            embedding BLOB,
            source_fact_ids TEXT DEFAULT '[]',
            history TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0
        )
    """)
    await conn.execute("""
        INSERT INTO observations_new (id, summary, embedding, source_fact_ids, history,
            created_at, updated_at, last_accessed_at, access_count)
        SELECT id, summary, embedding, source_fact_ids, history,
            created_at, updated_at, last_accessed_at, access_count
        FROM observations
    """)

    # Preserve FTS and vec data by dropping triggers first, then swapping
    await conn.execute("DROP TRIGGER IF EXISTS observations_ai")
    await conn.execute("DROP TRIGGER IF EXISTS observations_ad")
    await conn.execute("DROP TRIGGER IF EXISTS observations_au")

    await conn.execute("DROP TABLE observations")
    await conn.execute("ALTER TABLE observations_new RENAME TO observations")

    # Recreate triggers
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
            INSERT INTO observations_fts(rowid, summary) VALUES (new.id, new.summary);
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
            INSERT INTO observations_fts(observations_fts, rowid, summary) VALUES('delete', old.id, old.summary);
        END
    """)
    await conn.execute("""
        CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
            INSERT INTO observations_fts(observations_fts, rowid, summary) VALUES('delete', old.id, old.summary);
            INSERT INTO observations_fts(rowid, summary) VALUES (new.id, new.summary);
        END
    """)


async def _migrate_v3(conn: aiosqlite.Connection) -> None:
    """Add archived_at column to facts and observations for memory archival."""
    _logger.info("Migration v3: adding archived_at to facts and observations")

    for table in ("facts", "observations"):
        try:
            await conn.execute(f"ALTER TABLE {table} ADD COLUMN archived_at TIMESTAMP")
        except aiosqlite.OperationalError:
            pass  # Column already exists (fresh install)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_archived ON facts(archived_at)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_archived ON observations(archived_at)")


async def _migrate_v4(conn: aiosqlite.Connection) -> None:
    """Add ON DELETE CASCADE to obs_entity_refs for entity_id."""
    _logger.info("Migration v4: adding ON DELETE CASCADE to obs_entity_refs")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS obs_entity_refs_new (
            observation_id INTEGER REFERENCES observations(id) ON DELETE CASCADE,
            entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
            PRIMARY KEY (observation_id, entity_id)
        )
    """)
    await conn.execute("INSERT OR IGNORE INTO obs_entity_refs_new SELECT * FROM obs_entity_refs")
    await conn.execute("DROP TABLE obs_entity_refs")
    await conn.execute("ALTER TABLE obs_entity_refs_new RENAME TO obs_entity_refs")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_entity_refs_entity ON obs_entity_refs(entity_id)")


_MIGRATIONS: list[tuple[int, callable]] = [
    (1, _migrate_v1),
    (2, _migrate_v2),
    (3, _migrate_v3),
    (4, _migrate_v4),
]


async def run_migrations(conn: aiosqlite.Connection) -> None:
    current = await _get_version(conn)
    if current >= CURRENT_VERSION:
        return

    for version, migrate_fn in _MIGRATIONS:
        if version <= current:
            continue
        _logger.info("Running memory schema migration v%d", version)
        await migrate_fn(conn)
        await _set_version(conn, version)
        await conn.commit()

    _logger.info("Vacuuming database after migrations")
    await conn.execute("VACUUM")
    await conn.commit()
    _logger.info("Memory schema up to date (v%d)", CURRENT_VERSION)
