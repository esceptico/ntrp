from pathlib import Path

import aiosqlite
import pytest

import ntrp.database as database
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.migrations import CURRENT_VERSION, run_migrations
from tests.conftest import TEST_EMBEDDING_DIM

OLD_V4_FACTS_SCHEMA = """
    CREATE TABLE facts (
        id INTEGER PRIMARY KEY,
        text TEXT NOT NULL,
        embedding BLOB,
        source_type TEXT NOT NULL,
        source_ref TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        happened_at TIMESTAMP,
        last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        access_count INTEGER DEFAULT 0,
        consolidated_at TIMESTAMP,
        archived_at TIMESTAMP
    );
"""


@pytest.mark.asyncio
async def test_migrate_v5_adds_typed_fact_columns(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(f"""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '4');

        {OLD_V4_FACTS_SCHEMA}
    """)

    await run_migrations(conn)

    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    assert {
        "kind",
        "salience",
        "confidence",
        "expires_at",
        "pinned_at",
        "superseded_by_fact_id",
    }.issubset(columns)

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_init_schema_migrates_existing_v4_database(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db", vec=True)
    await conn.executescript(f"""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '4');
        {OLD_V4_FACTS_SCHEMA}
    """)

    db = GraphDatabase(conn, TEST_EMBEDDING_DIM)
    await db.init_schema()

    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    assert "kind" in columns
    assert "lifetime" in columns

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v13_adds_lifetime_and_backfills_legacy_temporary(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '12');

        CREATE TABLE facts (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            source_type TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'note',
            expires_at TIMESTAMP
        );
        INSERT INTO facts (id, text, source_type, kind) VALUES (1, 'Durable note', 'explicit', 'note');
        INSERT INTO facts (id, text, source_type, kind, expires_at)
        VALUES (2, 'Legacy temporary', 'explicit', 'temporary', '2026-05-02T00:00:00+00:00');
        INSERT INTO facts (id, text, source_type, kind, expires_at)
        VALUES (3, 'Expiring note', 'explicit', 'note', '2026-05-02T00:00:00+00:00');
        INSERT INTO facts (id, text, source_type, kind) VALUES (4, 'Legacy temporary without expiry', 'explicit', 'temporary');
    """)

    await run_migrations(conn)

    rows = await conn.execute_fetchall("SELECT id, kind, lifetime FROM facts ORDER BY id")
    assert [(row["id"], row["kind"], row["lifetime"]) for row in rows] == [
        (1, "note", "durable"),
        (2, "note", "temporary"),
        (3, "note", "temporary"),
        (4, "note", "durable"),
    ]
    indexes = {row["name"] for row in await conn.execute_fetchall("PRAGMA index_list(facts)")}
    assert "idx_facts_lifetime" in indexes

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v6_backfills_observation_provenance(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '5');

        CREATE TABLE facts (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            source_type TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'note',
            salience INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 1.0
        );
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL,
            source_fact_ids TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO facts (id, text, source_type) VALUES (1, 'Fact 1', 'explicit');
        INSERT INTO facts (id, text, source_type) VALUES (2, 'Fact 2', 'explicit');
        INSERT INTO observations (id, summary, source_fact_ids) VALUES (10, 'Observation', '[1,999,2]');
    """)

    await run_migrations(conn)

    observation_rows = await conn.execute_fetchall(
        "SELECT observation_id, fact_id FROM observation_facts ORDER BY fact_id"
    )
    assert [(row["observation_id"], row["fact_id"]) for row in observation_rows] == [(10, 1), (10, 2)]

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v8_adds_observation_policy_metadata(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '7');

        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL,
            source_fact_ids TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO observations (id, summary) VALUES (1, 'Legacy pattern');
    """)

    await run_migrations(conn)

    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(observations)")}
    assert {"created_by", "policy_version"}.issubset(columns)

    rows = await conn.execute_fetchall("SELECT created_by, policy_version FROM observations WHERE id = 1")
    assert dict(rows[0]) == {"created_by": "legacy", "policy_version": "legacy"}

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_init_schema_migrates_existing_v7_observations(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db", vec=True)
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '7');

        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL,
            embedding BLOB,
            source_fact_ids TEXT DEFAULT '[]',
            history TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            archived_at TIMESTAMP
        );
        INSERT INTO observations (id, summary) VALUES (1, 'Legacy pattern');
    """)

    db = GraphDatabase(conn, TEST_EMBEDDING_DIM)
    await db.init_schema()

    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(observations)")}
    assert {"created_by", "policy_version"}.issubset(columns)

    indexes = {row["name"] for row in await conn.execute_fetchall("PRAGMA index_list(observations)")}
    assert "idx_observations_policy" in indexes

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v9_adds_memory_access_events(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '8');
    """)

    await run_migrations(conn)

    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(memory_access_events)")}
    assert {
        "source",
        "query",
        "retrieved_fact_ids",
        "retrieved_observation_ids",
        "injected_fact_ids",
        "injected_observation_ids",
        "omitted_fact_ids",
        "omitted_observation_ids",
        "bundled_fact_ids",
        "formatted_chars",
        "policy_version",
        "details",
    }.issubset(columns)

    indexes = {row["name"] for row in await conn.execute_fetchall("PRAGMA index_list(memory_access_events)")}
    assert {"idx_memory_access_events_created", "idx_memory_access_events_source"}.issubset(indexes)

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_does_not_recreate_removed_memory_tables(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '9');
    """)

    await run_migrations(conn)

    tables = {row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "learning_events" not in tables
    assert "learning_candidates" not in tables
    assert "learning_candidate_events" not in tables
    assert "learning_event_processing" not in tables
    assert "profile_entries" not in tables

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v16_drops_existing_dream_and_learning_tables(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '15');
        CREATE TABLE dreams (
            id INTEGER PRIMARY KEY,
            bridge TEXT NOT NULL,
            insight TEXT NOT NULL,
            source_fact_ids TEXT DEFAULT '[]'
        );
        CREATE TABLE dream_facts (
            dream_id INTEGER NOT NULL,
            fact_id INTEGER NOT NULL,
            PRIMARY KEY (dream_id, fact_id)
        );
        CREATE TABLE learning_events (
            id INTEGER PRIMARY KEY,
            source_type TEXT NOT NULL,
            scope TEXT NOT NULL,
            signal TEXT NOT NULL
        );
        CREATE TABLE learning_candidates (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'proposed'
        );
        CREATE TABLE learning_candidate_events (
            candidate_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            PRIMARY KEY (candidate_id, event_id)
        );
        CREATE TABLE learning_event_processing (
            scanner TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            PRIMARY KEY (scanner, event_id)
        );
    """)

    await run_migrations(conn)

    tables = {row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "dreams" not in tables
    assert "dream_facts" not in tables
    assert "learning_events" not in tables
    assert "learning_candidates" not in tables
    assert "learning_candidate_events" not in tables
    assert "learning_event_processing" not in tables

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v17_drops_existing_profile_table(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '16');
        CREATE TABLE profile_entries (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            summary TEXT NOT NULL
        );
    """)

    await run_migrations(conn)

    tables = {row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "profile_entries" not in tables

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v18_adds_fact_validity_window(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '17');
        CREATE TABLE facts (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            source_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            happened_at TIMESTAMP
        );
        INSERT INTO facts (id, text, source_type, created_at, happened_at)
        VALUES (1, 'Created-only fact', 'explicit', '2026-05-01T10:00:00+00:00', NULL);
        INSERT INTO facts (id, text, source_type, created_at, happened_at)
        VALUES (2, 'Event fact', 'explicit', '2026-05-02T10:00:00+00:00', '2026-04-20T09:00:00+00:00');
    """)

    await run_migrations(conn)

    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(facts)")}
    assert {"valid_from", "valid_until"}.issubset(columns)

    rows = await conn.execute_fetchall("SELECT id, valid_from, valid_until FROM facts ORDER BY id")
    assert [(row["id"], row["valid_from"], row["valid_until"]) for row in rows] == [
        (1, "2026-05-01T10:00:00+00:00", None),
        (2, "2026-04-20T09:00:00+00:00", None),
    ]

    indexes = {row["name"] for row in await conn.execute_fetchall("PRAGMA index_list(facts)")}
    assert {"idx_facts_valid_from", "idx_facts_valid_until"}.issubset(indexes)

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()
