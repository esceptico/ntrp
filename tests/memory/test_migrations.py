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

    link_columns = {
        row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(learning_candidate_events)")
    }
    assert {"candidate_id", "event_id"}.issubset(link_columns)

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v14_rejects_deprecated_profile_learning_candidates(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '13');
        CREATE TABLE learning_candidates (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'proposed',
            change_type TEXT NOT NULL,
            target_key TEXT NOT NULL,
            proposal TEXT NOT NULL,
            rationale TEXT NOT NULL,
            evidence_event_ids TEXT NOT NULL DEFAULT '[]',
            expected_metric TEXT,
            policy_version TEXT NOT NULL,
            applied_at TIMESTAMP,
            reverted_at TIMESTAMP,
            details TEXT NOT NULL DEFAULT '{}'
        );
        INSERT INTO learning_candidates (
            status, change_type, target_key, proposal, rationale, policy_version
        ) VALUES
            ('proposed', 'profile_rule', 'memory.profile.promotions', 'old profile', 'old', 'test'),
            ('approved', 'supersession_review', 'memory.facts.supersession.profile', 'old conflict', 'old', 'test'),
            ('proposed', 'injection_rule', 'memory.injection.budget', 'keep', 'keep', 'test');
    """)

    await run_migrations(conn)

    rows = await conn.execute_fetchall("SELECT change_type, status FROM learning_candidates ORDER BY id")
    assert [(row["change_type"], row["status"]) for row in rows] == [
        ("profile_rule", "rejected"),
        ("supersession_review", "rejected"),
        ("injection_rule", "proposed"),
    ]

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()
