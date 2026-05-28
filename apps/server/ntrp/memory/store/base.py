import sqlite3

import aiosqlite

from ntrp.logging import get_logger
from ntrp.memory.store.migrations import run_migrations

_logger = get_logger(__name__)
MEMORY_ITEMS_SCHEMA_VERSION = 31

SCHEMA = """
-- Observations (consolidated patterns from facts)
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    summary TEXT NOT NULL,
    embedding BLOB,
    source_fact_ids TEXT DEFAULT '[]',  -- JSON array of fact IDs
    history TEXT DEFAULT '[]',          -- JSON array of changes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    archived_at TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'legacy',
    policy_version TEXT NOT NULL DEFAULT 'legacy'
);

CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
    summary,
    content='observations',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
    INSERT INTO observations_fts(rowid, summary) VALUES (new.id, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, summary) VALUES('delete', old.id, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, summary) VALUES('delete', old.id, old.summary);
    INSERT INTO observations_fts(rowid, summary) VALUES (new.id, new.summary);
END;

-- Fact-centric tables

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    embedding BLOB,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    happened_at TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    consolidated_at TIMESTAMP,  -- NULL = not yet consolidated
    archived_at TIMESTAMP,
    kind TEXT NOT NULL DEFAULT 'note',
    lifetime TEXT NOT NULL DEFAULT 'durable',
    salience INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1.0,
    expires_at TIMESTAMP,
    pinned_at TIMESTAMP,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP,
    superseded_by_fact_id INTEGER REFERENCES facts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_facts_created ON facts(created_at DESC);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    entity_type TEXT NOT NULL DEFAULT 'other',
    lifecycle_status TEXT NOT NULL DEFAULT 'active',
    merged_into_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entity_refs (
    id INTEGER PRIMARY KEY,
    fact_id INTEGER REFERENCES facts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_entity_refs_fact ON entity_refs(fact_id);
CREATE INDEX IF NOT EXISTS idx_entity_refs_name ON entity_refs(name);
CREATE INDEX IF NOT EXISTS idx_entity_refs_entity ON entity_refs(entity_id);

CREATE TABLE IF NOT EXISTS obs_entity_refs (
    observation_id INTEGER REFERENCES observations(id) ON DELETE CASCADE,
    entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (observation_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_obs_entity_refs_entity ON obs_entity_refs(entity_id);

CREATE INDEX IF NOT EXISTS idx_facts_consolidated ON facts(consolidated_at);

CREATE TABLE IF NOT EXISTS temporal_checkpoints (
    entity_id INTEGER REFERENCES entities(id),
    window_end TIMESTAMP,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_id, window_end)
);

CREATE TABLE IF NOT EXISTS observation_facts (
    observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'support',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (observation_id, fact_id)
);

CREATE INDEX IF NOT EXISTS idx_observation_facts_fact ON observation_facts(fact_id);

CREATE TABLE IF NOT EXISTS memory_events (
    id INTEGER PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    source_type TEXT,
    source_ref TEXT,
    reason TEXT,
    policy_version TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memory_events_created ON memory_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_events_target ON memory_events(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_memory_events_action ON memory_events(action);

CREATE TABLE IF NOT EXISTS memory_access_events (
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

CREATE INDEX IF NOT EXISTS idx_memory_access_events_created ON memory_access_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_access_events_source ON memory_access_events(source);

CREATE TABLE IF NOT EXISTS knowledge_objects (
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
    superseded_by_object_id INTEGER REFERENCES knowledge_objects(id) ON DELETE SET NULL,
    superseded_at TIMESTAMP,
    supersession_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_knowledge_objects_type_status ON knowledge_objects(object_type, status);
CREATE INDEX IF NOT EXISTS idx_knowledge_objects_updated ON knowledge_objects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_objects_scope ON knowledge_objects(scope);

CREATE TABLE IF NOT EXISTS knowledge_entity_refs (
    knowledge_object_id INTEGER NOT NULL REFERENCES knowledge_objects(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (knowledge_object_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_entity_refs_entity ON knowledge_entity_refs(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_entity_refs_name ON knowledge_entity_refs(name);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id INTEGER PRIMARY KEY,
    knowledge_object_id INTEGER NOT NULL REFERENCES knowledge_objects(id) ON DELETE CASCADE,
    entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
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

CREATE INDEX IF NOT EXISTS idx_entity_mentions_object ON entity_mentions(knowledge_object_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_surface ON entity_mentions(normalized_surface);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_status ON entity_mentions(resolution_status);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    alias_text TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'extracted',
    source_mention_id INTEGER REFERENCES entity_mentions(id) ON DELETE SET NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    scope TEXT,
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_lookup ON entity_aliases(normalized_alias, status);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);

CREATE TABLE IF NOT EXISTS entity_resolution_candidates (
    id INTEGER PRIMARY KEY,
    mention_id INTEGER NOT NULL REFERENCES entity_mentions(id) ON DELETE CASCADE,
    candidate_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    method TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.0,
    features TEXT NOT NULL DEFAULT '{}',
    rank INTEGER,
    decision_status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entity_resolution_candidates_mention ON entity_resolution_candidates(mention_id);
CREATE INDEX IF NOT EXISTS idx_entity_resolution_candidates_entity ON entity_resolution_candidates(candidate_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_resolution_candidates_status ON entity_resolution_candidates(decision_status);

CREATE TABLE IF NOT EXISTS entity_resolution_commits (
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

CREATE INDEX IF NOT EXISTS idx_entity_resolution_commits_action ON entity_resolution_commits(action);
CREATE INDEX IF NOT EXISTS idx_entity_resolution_commits_created ON entity_resolution_commits(created_at DESC);

CREATE TABLE IF NOT EXISTS entity_identity_edges (
    id INTEGER PRIMARY KEY,
    entity_a_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    entity_b_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    evidence TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    commit_id INTEGER REFERENCES entity_resolution_commits(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entity_identity_edges_entities ON entity_identity_edges(entity_a_id, entity_b_id);
CREATE INDEX IF NOT EXISTS idx_entity_identity_edges_relation ON entity_identity_edges(relation, status);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_objects_fts USING fts5(
    title,
    text,
    content='knowledge_objects',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS knowledge_objects_ai AFTER INSERT ON knowledge_objects BEGIN
    INSERT INTO knowledge_objects_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_objects_ad AFTER DELETE ON knowledge_objects BEGIN
    INSERT INTO knowledge_objects_fts(knowledge_objects_fts, rowid, title, text) VALUES('delete', old.id, old.title, old.text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_objects_au AFTER UPDATE ON knowledge_objects BEGIN
    INSERT INTO knowledge_objects_fts(knowledge_objects_fts, rowid, title, text) VALUES('delete', old.id, old.title, old.text);
    INSERT INTO knowledge_objects_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    text,
    content='facts',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.id, old.text);
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


class GraphDatabase:
    def __init__(self, conn: aiosqlite.Connection, embedding_dim: int):
        self.conn = conn
        self.embedding_dim = embedding_dim
        self.dim_changed = False

    async def init_schema(self) -> None:
        await self.conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        stored_schema_version = await self._get_meta("schema_version")
        try:
            schema_version = int(stored_schema_version) if stored_schema_version is not None else 0
        except ValueError:
            schema_version = 0
        if schema_version < MEMORY_ITEMS_SCHEMA_VERSION:
            await self.conn.executescript(SCHEMA)
            await self.conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        await run_migrations(self.conn)

        stored_dim = await self._get_meta("embedding_dim")
        if stored_dim is None or int(stored_dim) != self.embedding_dim:
            _logger.info(
                "Rebuilding memory vec tables (stored=%s, current=%d)",
                stored_dim,
                self.embedding_dim,
            )
            await self.conn.execute("DROP TABLE IF EXISTS observations_vec")
            await self.conn.execute("DROP TABLE IF EXISTS facts_vec")
            await self.conn.execute("DROP TABLE IF EXISTS knowledge_objects_vec")
            await self.conn.execute("DROP TABLE IF EXISTS memory_items_vec")
            # Only trigger re-embed when there's existing data with stale embeddings
            old_embedding_tables = {
                row[0]
                for row in await self.conn.execute_fetchall(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)",
                    ("facts", "observations", "knowledge_objects"),
                )
            }
            stale_embedding_queries = []
            if "facts" in old_embedding_tables:
                stale_embedding_queries.append("SELECT 1 FROM facts WHERE embedding IS NOT NULL")
            if "observations" in old_embedding_tables:
                stale_embedding_queries.append("SELECT 1 FROM observations WHERE embedding IS NOT NULL")
            if "knowledge_objects" in old_embedding_tables:
                stale_embedding_queries.append("SELECT 1 FROM knowledge_objects WHERE embedding IS NOT NULL")
            if stale_embedding_queries:
                rows = await self.conn.execute_fetchall(f"""
                    SELECT EXISTS(
                        {" UNION ALL ".join(stale_embedding_queries)}
                    )
                """)
            else:
                rows = []
            if rows and rows[0][0]:
                self.dim_changed = True

        await self._init_vec_tables()
        await self._set_meta("embedding_dim", str(self.embedding_dim))
        await self.conn.commit()

    async def clear_all(self) -> None:
        await self.conn.execute("DELETE FROM memory_access_events")
        await self.conn.execute("DELETE FROM memory_events")
        await self.conn.execute("DELETE FROM knowledge_objects_vec")
        await self.conn.execute("DELETE FROM knowledge_entity_refs")
        await self.conn.execute("DELETE FROM knowledge_objects")
        await self.conn.execute("DELETE FROM temporal_checkpoints")
        await self.conn.execute("DELETE FROM obs_entity_refs")
        await self.conn.execute("DELETE FROM observation_facts")
        await self.conn.execute("DELETE FROM observations_vec")
        await self.conn.execute("DELETE FROM observations")
        await self.conn.execute("DELETE FROM entity_refs")
        await self.conn.execute("DELETE FROM entities")
        await self.conn.execute("DELETE FROM facts_vec")
        await self.conn.execute("DELETE FROM facts")
        await self.conn.commit()

    async def _init_vec_tables(self) -> None:
        dim = self.embedding_dim
        stored_schema_version = await self._get_meta("schema_version")
        try:
            schema_version = int(stored_schema_version) if stored_schema_version is not None else 0
        except ValueError:
            schema_version = 0
        create_legacy_vec_tables = schema_version < MEMORY_ITEMS_SCHEMA_VERSION
        vec_table_names = ("memory_items_vec",)
        if create_legacy_vec_tables:
            vec_table_names = ("observations_vec", "facts_vec", "knowledge_objects_vec", "memory_items_vec")
        existing = {
            row[0]
            for row in await self.conn.execute_fetchall(
                f"""
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                  AND name IN ({",".join("?" for _ in vec_table_names)})
                """,
                vec_table_names,
            )
        }
        # sqlite-vec can spend a long time opening large existing virtual tables
        # even behind CREATE VIRTUAL TABLE IF NOT EXISTS. Check sqlite_master first
        # so startup migrations do not block on no-op vec table creation.
        async def create_vec_table(name: str, sql: str) -> None:
            try:
                await self.conn.execute(sql)
            except sqlite3.OperationalError as exc:
                if "no such module: vec0" in str(exc):
                    _logger.warning("sqlite-vec extension unavailable; skipping %s", name)
                    return
                raise

        if create_legacy_vec_tables and "observations_vec" not in existing:
            await create_vec_table(
                "observations_vec",
                f"""
                CREATE VIRTUAL TABLE observations_vec USING vec0(
                    observation_id INTEGER PRIMARY KEY,
                    embedding float[{dim}] distance_metric=cosine
                );
                """,
            )
        if create_legacy_vec_tables and "facts_vec" not in existing:
            await create_vec_table(
                "facts_vec",
                f"""
                CREATE VIRTUAL TABLE facts_vec USING vec0(
                    fact_id INTEGER PRIMARY KEY,
                    embedding float[{dim}] distance_metric=cosine
                );
                """,
            )
        if create_legacy_vec_tables and "knowledge_objects_vec" not in existing:
            await create_vec_table(
                "knowledge_objects_vec",
                f"""
                CREATE VIRTUAL TABLE knowledge_objects_vec USING vec0(
                    knowledge_object_id INTEGER PRIMARY KEY,
                    embedding float[{dim}] distance_metric=cosine
                );
                """,
            )
        if "memory_items_vec" not in existing:
            await create_vec_table(
                "memory_items_vec",
                f"""
                CREATE VIRTUAL TABLE memory_items_vec USING vec0(
                    item_id TEXT PRIMARY KEY,
                    embedding float[{dim}] distance_metric=cosine
                );
                """,
            )

    async def _get_meta(self, key: str) -> str | None:
        try:
            rows = await self.conn.execute_fetchall("SELECT value FROM meta WHERE key = ?", (key,))
            return rows[0][0] if rows else None
        except Exception:
            return None

    async def _set_meta(self, key: str, value: str) -> None:
        await self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    async def rebuild_vec_tables(self, new_dim: int) -> None:
        self.embedding_dim = new_dim
        await self.conn.execute("DROP TABLE IF EXISTS observations_vec")
        await self.conn.execute("DROP TABLE IF EXISTS facts_vec")
        await self.conn.execute("DROP TABLE IF EXISTS knowledge_objects_vec")
        await self.conn.execute("DROP TABLE IF EXISTS memory_items_vec")
        await self._init_vec_tables()
        await self._set_meta("embedding_dim", str(new_dim))
        await self.conn.commit()
