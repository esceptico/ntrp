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


@pytest.mark.asyncio
async def test_migrate_v21_adds_and_backfills_knowledge_object_fts(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '20');
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        );
        INSERT INTO knowledge_objects (id, object_type, title, text, status)
        VALUES (1, 'fact', 'Rare durable memory', 'needle_rare_token_zzzz is indexed after migration.', 'active');
    """)

    await run_migrations(conn)

    tables = {row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "knowledge_objects_fts" in tables
    rows = await conn.execute_fetchall(
        """
        SELECT ko.id
        FROM knowledge_objects_fts
        JOIN knowledge_objects ko ON ko.id = knowledge_objects_fts.rowid
        WHERE knowledge_objects_fts MATCH 'needle_rare_token_zzzz'
        """
    )
    assert [row["id"] for row in rows] == [1]

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v23_adds_schema_level_knowledge_object_supersession(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '22');
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            embedding BLOB,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        );
        INSERT INTO knowledge_objects (id, object_type, title, text, status, metadata, updated_at)
        VALUES (1, 'fact', 'Old policy', 'Old policy', 'active', '{"superseded_by_object_id":2,"supersession_reason":"newer fact"}', '2026-05-01T00:00:00+00:00');
        INSERT INTO knowledge_objects (id, object_type, title, text, status)
        VALUES (2, 'fact', 'New policy', 'New policy', 'active');
    """)

    await run_migrations(conn)

    columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(knowledge_objects)")}
    assert {"superseded_by_object_id", "superseded_at", "supersession_reason"}.issubset(columns)

    rows = await conn.execute_fetchall(
        "SELECT status, superseded_by_object_id, superseded_at, supersession_reason FROM knowledge_objects WHERE id = 1"
    )
    assert dict(rows[0]) == {
        "status": "superseded",
        "superseded_by_object_id": 2,
        "superseded_at": "2026-05-01T00:00:00+00:00",
        "supersession_reason": "newer fact",
    }

    indexes = {row["name"] for row in await conn.execute_fetchall("PRAGMA index_list(knowledge_objects)")}
    assert "idx_knowledge_objects_superseded" in indexes

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v24_backfills_normalized_knowledge_entity_refs(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '23');
        CREATE TABLE entities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            embedding BLOB,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            superseded_by_object_id INTEGER,
            superseded_at TIMESTAMP,
            supersession_reason TEXT
        );
        INSERT INTO knowledge_objects (id, object_type, title, text, status, metadata)
        VALUES (1, 'procedure', 'Prime Intellect cleanup', 'Uses Trigger.dev', 'active', '{"entities":["Prime Intellect"],"entity_graph":{"entities":["Trigger.dev"]}}');
    """)

    await run_migrations(conn)

    tables = {row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "knowledge_entity_refs" in tables

    rows = await conn.execute_fetchall(
        """
        SELECT ker.knowledge_object_id, e.name
        FROM knowledge_entity_refs ker
        JOIN entities e ON e.id = ker.entity_id
        ORDER BY e.name
        """
    )
    assert [(row["knowledge_object_id"], row["name"]) for row in rows] == [
        (1, "Prime Intellect"),
        (1, "Trigger.dev"),
    ]

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v25_adds_entity_resolution_identity_layer(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '24');
        CREATE TABLE entities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_entity_refs (
            knowledge_object_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (knowledge_object_id, entity_id)
        );
        INSERT INTO entities (id, name) VALUES (1, 'Trigger.dev');
    """)

    await run_migrations(conn)

    tables = {row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "entity_mentions",
        "entity_aliases",
        "entity_resolution_candidates",
        "entity_identity_edges",
        "entity_resolution_commits",
    }.issubset(tables)

    entity_columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(entities)")}
    assert {"entity_type", "lifecycle_status", "merged_into_entity_id", "metadata"}.issubset(entity_columns)

    aliases = await conn.execute_fetchall("SELECT entity_id, alias_text, alias_type FROM entity_aliases")
    assert [(row["entity_id"], row["alias_text"], row["alias_type"]) for row in aliases] == [
        (1, "Trigger.dev", "canonical")
    ]

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)

    await conn.close()


@pytest.mark.asyncio
async def test_init_schema_handles_live_v20_knowledge_schema(tmp_path: Path):
    from ntrp.memory.store.base import GraphDatabase

    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '20');
        CREATE TABLE entities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        );
        INSERT INTO knowledge_objects (id, object_type, title, text, status)
        VALUES (1, 'episode', 'Legacy run episode', 'Legacy raw run evidence.', 'active');
    """)

    db = GraphDatabase(conn, embedding_dim=1536)
    await db.init_schema()

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)
    knowledge_columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(knowledge_objects)")}
    assert {"embedding", "superseded_by_object_id", "superseded_at", "supersession_reason"}.issubset(knowledge_columns)
    entity_columns = {row["name"] for row in await conn.execute_fetchall("PRAGMA table_info(entities)")}
    assert {"entity_type", "lifecycle_status", "merged_into_entity_id", "metadata"}.issubset(entity_columns)
    tables = {row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"knowledge_objects_fts", "knowledge_entity_refs", "entity_mentions", "entity_aliases"}.issubset(tables)

    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v26_archives_legacy_reflect_spam_and_prunes_identifier_entities(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '25');
        CREATE TABLE entities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            entity_type TEXT NOT NULL DEFAULT 'other',
            lifecycle_status TEXT NOT NULL DEFAULT 'active',
            merged_into_entity_id INTEGER,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            embedding BLOB,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            superseded_by_object_id INTEGER,
            superseded_at TIMESTAMP,
            supersession_reason TEXT
        );
        CREATE TABLE knowledge_entity_refs (
            knowledge_object_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (knowledge_object_id, entity_id)
        );
        CREATE TABLE entity_mentions (
            id INTEGER PRIMARY KEY,
            knowledge_object_id INTEGER NOT NULL,
            entity_id INTEGER,
            surface_text TEXT NOT NULL,
            normalized_surface TEXT NOT NULL,
            canonical_name TEXT,
            entity_type_hint TEXT NOT NULL DEFAULT 'other',
            evidence_quote TEXT,
            extraction_confidence REAL NOT NULL DEFAULT 0.0,
            resolution_confidence REAL,
            resolution_status TEXT NOT NULL DEFAULT 'unresolved',
            extractor TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'extractor',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE entity_aliases (
            id INTEGER PRIMARY KEY,
            entity_id INTEGER NOT NULL,
            alias_text TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            alias_type TEXT NOT NULL DEFAULT 'extracted',
            source_mention_id INTEGER,
            confidence REAL NOT NULL DEFAULT 0.0,
            scope TEXT,
            valid_from TIMESTAMP,
            valid_to TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE entity_resolution_candidates (
            id INTEGER PRIMARY KEY,
            mention_id INTEGER NOT NULL,
            candidate_entity_id INTEGER,
            method TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,
            features TEXT NOT NULL DEFAULT '{}',
            rank INTEGER,
            decision_status TEXT NOT NULL DEFAULT 'proposed',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE entity_identity_edges (
            id INTEGER PRIMARY KEY,
            entity_a_id INTEGER NOT NULL,
            entity_b_id INTEGER NOT NULL,
            relation TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            evidence TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            commit_id INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE entity_resolution_commits (
            id INTEGER PRIMARY KEY,
            action TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            before_entity_ids TEXT NOT NULL DEFAULT '[]',
            after_entity_ids TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '{}',
            reversible_patch TEXT NOT NULL DEFAULT '{}',
            confidence REAL,
            rule_version TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO knowledge_objects (id, object_type, title, text, status, metadata)
        VALUES (10, 'episode', 'Run noisy', 'Session: 20260510_235813_387', 'active', '{}');
        INSERT INTO knowledge_objects (id, object_type, title, text, status, metadata, source_ids)
        VALUES (11, 'fact', 'Fact from Run noisy', 'Session: 20260510_235813_387', 'active', '{"processor":"reflect","episode_id":10}', '["knowledge:10"]');
        INSERT INTO knowledge_objects (id, object_type, title, text, status, metadata)
        VALUES (12, 'fact', 'Real fact', 'Durable fact.', 'active', '{}');
        INSERT INTO entities (id, name) VALUES (1, 'session:20260510_235813_387'), (2, '1628'), (3, 'Trigger.dev');
        INSERT INTO knowledge_entity_refs (knowledge_object_id, entity_id, name) VALUES (11, 1, 'session:20260510_235813_387'), (11, 2, '1628'), (12, 3, 'Trigger.dev');
        INSERT INTO entity_aliases (entity_id, alias_text, normalized_alias) VALUES (1, 'session:20260510_235813_387', 'session:20260510_235813_387'), (3, 'Trigger.dev', 'trigger.dev');
        INSERT INTO entity_mentions (id, knowledge_object_id, entity_id, surface_text, normalized_surface, extractor) VALUES (1, 11, 1, 'session:20260510_235813_387', 'session:20260510_235813_387', 'test');
        INSERT INTO entity_resolution_candidates (mention_id, candidate_entity_id, method) VALUES (1, 1, 'test');
        INSERT INTO entity_identity_edges (entity_a_id, entity_b_id, relation) VALUES (1, 3, 'related_to');
    """)

    await run_migrations(conn)

    spam = await conn.execute_fetchall("SELECT status, json_extract(metadata, '$.archived_reason') AS reason FROM knowledge_objects WHERE id = 11")
    assert dict(spam[0]) == {"status": "archived", "reason": "legacy_reflect_spam"}
    entity_names = [row["name"] for row in await conn.execute_fetchall("SELECT name FROM entities ORDER BY id")]
    assert entity_names == ["Trigger.dev"]
    refs = await conn.execute_fetchall("SELECT entity_id FROM knowledge_entity_refs")
    assert [row["entity_id"] for row in refs] == [3]

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)
    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v27_exposes_source_and_metadata_views(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '26');
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            superseded_by_object_id INTEGER,
            superseded_at TIMESTAMP,
            supersession_reason TEXT
        );
        INSERT INTO knowledge_objects (id, object_type, title, text, status, source_ids, metadata)
        VALUES (1, 'memory_episode', 'Source episode', 'Episode text', 'closed', '[]', '{}');
        INSERT INTO knowledge_objects (id, object_type, title, text, status, source_ids, metadata)
        VALUES (
            2,
            'fact',
            'Fact',
            'Fact text',
            'active',
            '["knowledge:1","email:abc"]',
            '{"source_episode_id":1,"source_run_ids":["run-a"],"source_turn_ids":["turn-a"],"kind":"preference"}'
        );
    """)

    await run_migrations(conn)

    sources = await conn.execute_fetchall("""
        SELECT source_field, source_kind, source_id, source_object_id, source_title
        FROM knowledge_object_source_refs
        WHERE knowledge_object_id = 2
        ORDER BY source_field, source_id
    """)
    source_rows = [dict(row) for row in sources]
    assert {
        "source_field": "source_ids",
        "source_kind": "knowledge",
        "source_id": "knowledge:1",
        "source_object_id": 1,
        "source_title": "Source episode",
    } in source_rows
    assert {
        "source_field": "source_ids",
        "source_kind": "email",
        "source_id": "email:abc",
        "source_object_id": None,
        "source_title": None,
    } in source_rows
    assert any(row["source_field"] == "metadata.source_run_ids" and row["source_id"] == "run:run-a" for row in source_rows)
    assert any(row["source_field"] == "metadata.source_turn_ids" and row["source_id"] == "turn:turn-a" for row in source_rows)

    details = await conn.execute_fetchall("""
        SELECT metadata_key, value_type, value
        FROM knowledge_object_metadata_entries
        WHERE knowledge_object_id = 2 AND metadata_key = 'kind'
    """)
    assert dict(details[0]) == {"metadata_key": "kind", "value_type": "text", "value": "preference"}

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)
    await conn.close()


@pytest.mark.asyncio
async def test_migrate_v28_archives_activation_telemetry_and_exposes_activation_items(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '27');
        CREATE TABLE knowledge_objects (
            id INTEGER PRIMARY KEY,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            scope TEXT,
            activation TEXT NOT NULL DEFAULT 'prompt',
            proactiveness_level TEXT NOT NULL DEFAULT 'L0',
            score REAL NOT NULL DEFAULT 0.0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            superseded_by_object_id INTEGER,
            superseded_at TIMESTAMP,
            supersession_reason TEXT
        );
        CREATE TABLE memory_access_events (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL,
            query TEXT,
            retrieved_fact_ids TEXT NOT NULL DEFAULT '[]',
            retrieved_observation_ids TEXT NOT NULL DEFAULT '[]',
            injected_fact_ids TEXT NOT NULL DEFAULT '[]',
            injected_observation_ids TEXT NOT NULL DEFAULT '[]',
            omitted_fact_ids TEXT NOT NULL DEFAULT '[]',
            omitted_observation_ids TEXT NOT NULL DEFAULT '[]',
            bundled_fact_ids TEXT NOT NULL DEFAULT '[]',
            formatted_chars INTEGER NOT NULL DEFAULT 0,
            policy_version TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}'
        );
        INSERT INTO knowledge_objects (id, object_type, title, text, status, metadata)
        VALUES (1, 'outcome_feedback', 'Activation: chat_prompt', 'Activated knowledge', 'active', '{"kind":"activation_access"}');
        INSERT INTO knowledge_objects (id, object_type, title, text, status, metadata)
        VALUES (2, 'fact', 'Memory fact', 'Memory activation traces exist.', 'active', '{}');
        INSERT INTO memory_access_events (id, source, query, retrieved_fact_ids, injected_fact_ids, omitted_fact_ids, formatted_chars, policy_version, details)
        VALUES (
            10,
            'chat_prompt',
            'what do we have in activations',
            '[2,3]',
            '[2]',
            '[3]',
            128,
            'knowledge.activation.v2',
            '{"candidates":[{"rank":1,"object_id":"2","object_type":"fact","score":0.9,"selected":true,"injected":true,"activation":"prompt","proactiveness_level":"L0","chars":31,"reasons":["memory_system_query"],"signals":[],"source_ids":["knowledge:source"]}],"omitted":[{"rank":1,"object_id":"3","object_type":"pattern","score":0.1,"selected":false,"injected":false,"reasons":["budget_exceeded"],"signals":[],"source_ids":[]}]}'
        );
        INSERT INTO memory_access_events (id, source, query, retrieved_fact_ids, injected_fact_ids, formatted_chars, policy_version, details)
        VALUES (
            11,
            'chat_prompt',
            'legacy activation event',
            '[2]',
            '[2]',
            64,
            'knowledge.activation.v1',
            '{"candidate_ids":["2"],"candidate_types":["fact"],"injected":true}'
        );
    """)

    await run_migrations(conn)

    archived = await conn.execute_fetchall("""
        SELECT status, json_extract(metadata, '$.archived_reason') AS reason
        FROM knowledge_objects WHERE id = 1
    """)
    assert dict(archived[0]) == {"status": "archived", "reason": "activation_access_telemetry"}

    rows = await conn.execute_fetchall("""
        SELECT access_event_id, knowledge_object_id, object_type, score, selected, injected, reasons, object_title
        FROM knowledge_activation_items
        ORDER BY access_event_id, selected DESC, rank
    """)
    assert dict(rows[0]) == {
        "access_event_id": 10,
        "knowledge_object_id": 2,
        "object_type": "fact",
        "score": 0.9,
        "selected": 1,
        "injected": 1,
        "reasons": '["memory_system_query"]',
        "object_title": "Memory fact",
    }
    assert dict(rows[1]) == {
        "access_event_id": 10,
        "knowledge_object_id": 3,
        "object_type": "pattern",
        "score": 0.1,
        "selected": 0,
        "injected": 0,
        "reasons": '["budget_exceeded"]',
        "object_title": None,
    }
    assert dict(rows[2]) == {
        "access_event_id": 11,
        "knowledge_object_id": 2,
        "object_type": "fact",
        "score": None,
        "selected": 1,
        "injected": 1,
        "reasons": None,
        "object_title": "Memory fact",
    }

    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)
    await conn.close()
