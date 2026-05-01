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

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v6_backfills_generated_memory_provenance(tmp_path: Path):
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
        CREATE TABLE dreams (
            id INTEGER PRIMARY KEY,
            bridge TEXT NOT NULL,
            insight TEXT NOT NULL,
            source_fact_ids TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        INSERT INTO facts (id, text, source_type) VALUES (1, 'Fact 1', 'explicit');
        INSERT INTO facts (id, text, source_type) VALUES (2, 'Fact 2', 'explicit');
        INSERT INTO observations (id, summary, source_fact_ids) VALUES (10, 'Observation', '[1,999,2]');
        INSERT INTO dreams (id, bridge, insight, source_fact_ids) VALUES (20, 'Bridge', 'Insight', '[2,999]');
    """)

    await run_migrations(conn)

    observation_rows = await conn.execute_fetchall(
        "SELECT observation_id, fact_id FROM observation_facts ORDER BY fact_id"
    )
    assert [(row["observation_id"], row["fact_id"]) for row in observation_rows] == [(10, 1), (10, 2)]

    dream_rows = await conn.execute_fetchall("SELECT dream_id, fact_id FROM dream_facts ORDER BY fact_id")
    assert [(row["dream_id"], row["fact_id"]) for row in dream_rows] == [(20, 2)]

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
async def test_migrate_v10_adds_learning_tables(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '9');
    """)

    await run_migrations(conn)

    event_columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(learning_events)")}
    assert {
        "source_type",
        "source_id",
        "scope",
        "signal",
        "evidence_ids",
        "outcome",
        "details",
    }.issubset(event_columns)

    candidate_columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(learning_candidates)")}
    assert {
        "status",
        "change_type",
        "target_key",
        "proposal",
        "rationale",
        "evidence_event_ids",
        "expected_metric",
        "policy_version",
        "applied_at",
        "reverted_at",
        "details",
    }.issubset(candidate_columns)

    indexes = {row["name"] for row in await conn.execute_fetchall("PRAGMA index_list(learning_candidates)")}
    assert {"idx_learning_candidates_status", "idx_learning_candidates_change_type"}.issubset(indexes)

    processing_columns = {
        row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(learning_event_processing)")
    }
    assert {"scanner", "event_id", "candidate_id", "decision", "processed_at"}.issubset(processing_columns)

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()
