from pathlib import Path

import aiosqlite
import pytest

import ntrp.database as database
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.migrations import CURRENT_VERSION, run_migrations
from tests.conftest import TEST_EMBEDDING_DIM

LEGACY_TABLES = {
    "facts",
    "observations",
    "knowledge_objects",
    "entities",
    "entity_aliases",
    "entity_identity_edges",
    "entity_mentions",
    "entity_refs",
    "entity_resolution_candidates",
    "entity_resolution_commits",
    "obs_entity_refs",
    "observation_facts",
    "knowledge_entity_refs",
    "memory_access_events",
    "memory_events",
    "temporal_checkpoints",
    "facts_fts",
    "observations_fts",
    "knowledge_objects_fts",
}

CORE_TABLES = {
    "memory_items",
    "memory_item_parents",
    "episode_buffers",
    "memory_items_fts",
}


async def _table_names(conn: aiosqlite.Connection) -> set[str]:
    rows = await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    return {row["name"] for row in rows}


async def _assert_v31_core(conn: aiosqlite.Connection) -> None:
    version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)
    tables = await _table_names(conn)
    assert CORE_TABLES.issubset(tables)
    assert LEGACY_TABLES.isdisjoint(tables)


@pytest.mark.asyncio
async def test_v31_migration_burns_pre_v31_tables(tmp_path: Path):
    conn = await aiosqlite.connect(tmp_path / "memory.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '30');

        CREATE TABLE facts (id INTEGER PRIMARY KEY, text TEXT NOT NULL);
        CREATE TABLE observations (id INTEGER PRIMARY KEY, summary TEXT NOT NULL);
        CREATE TABLE knowledge_objects (id INTEGER PRIMARY KEY, text TEXT NOT NULL);
        CREATE TABLE entities (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE memory_access_events (id INTEGER PRIMARY KEY);
        CREATE VIRTUAL TABLE facts_fts USING fts5(text);
        CREATE VIRTUAL TABLE observations_fts USING fts5(summary);
        CREATE VIRTUAL TABLE knowledge_objects_fts USING fts5(text);
    """)

    await run_migrations(conn)

    await _assert_v31_core(conn)
    await conn.close()


@pytest.mark.asyncio
async def test_init_schema_migrates_live_knowledge_schema_to_memory_items(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db", vec=True)
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
        VALUES (1, 'episode', 'Legacy episode', 'Legacy raw evidence.', 'active');
    """)
    db = GraphDatabase(conn, TEST_EMBEDDING_DIM)

    try:
        await db.init_schema()

        await _assert_v31_core(conn)
        assert "memory_items_vec" in await _table_names(conn)
    finally:
        await conn.close()
