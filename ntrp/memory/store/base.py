import aiosqlite

from ntrp.logging import get_logger

_logger = get_logger(__name__)

SCHEMA = """
-- Observations (consolidated patterns from facts)
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    summary TEXT NOT NULL,
    embedding BLOB,
    evidence_count INTEGER DEFAULT 0,
    source_fact_ids TEXT DEFAULT '[]',  -- JSON array of fact IDs
    history TEXT DEFAULT '[]',          -- JSON array of changes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0
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
    consolidated_at TIMESTAMP  -- NULL = not yet consolidated
);

CREATE INDEX IF NOT EXISTS idx_facts_created ON facts(created_at DESC);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entity_refs (
    id INTEGER PRIMARY KEY,
    fact_id INTEGER REFERENCES facts(id),
    name TEXT NOT NULL,
    entity_id INTEGER REFERENCES entities(id)
);

CREATE INDEX IF NOT EXISTS idx_entity_refs_fact ON entity_refs(fact_id);
CREATE INDEX IF NOT EXISTS idx_entity_refs_name ON entity_refs(name);
CREATE INDEX IF NOT EXISTS idx_entity_refs_entity ON entity_refs(entity_id);

CREATE INDEX IF NOT EXISTS idx_facts_consolidated ON facts(consolidated_at);

CREATE TABLE IF NOT EXISTS temporal_checkpoints (
    entity_id INTEGER REFERENCES entities(id),
    window_end TIMESTAMP,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_id, window_end)
);

CREATE TABLE IF NOT EXISTS dreams (
    id INTEGER PRIMARY KEY,
    bridge TEXT NOT NULL,
    insight TEXT NOT NULL,
    source_fact_ids TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
        await self.conn.executescript(SCHEMA)
        await self.conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )

        stored_dim = await self._get_meta("embedding_dim")
        if stored_dim is None or int(stored_dim) != self.embedding_dim:
            _logger.info(
                "Rebuilding memory vec tables (stored=%s, current=%d)",
                stored_dim,
                self.embedding_dim,
            )
            await self.conn.execute("DROP TABLE IF EXISTS observations_vec")
            await self.conn.execute("DROP TABLE IF EXISTS facts_vec")
            # Only trigger re-embed when there's existing data with stale embeddings
            rows = await self.conn.execute_fetchall(
                "SELECT EXISTS(SELECT 1 FROM facts WHERE embedding IS NOT NULL)"
            )
            if rows and rows[0][0]:
                self.dim_changed = True

        await self._init_vec_tables()
        await self._set_meta("embedding_dim", str(self.embedding_dim))
        await self.conn.commit()

    async def clear_all(self) -> None:
        await self.conn.execute("DELETE FROM dreams")
        await self.conn.execute("DELETE FROM temporal_checkpoints")
        await self.conn.execute("DELETE FROM observations_vec")
        await self.conn.execute("DELETE FROM observations")
        await self.conn.execute("DELETE FROM entity_refs")
        await self.conn.execute("DELETE FROM entities")
        await self.conn.execute("DELETE FROM facts_vec")
        await self.conn.execute("DELETE FROM facts")
        await self.conn.commit()

    async def _init_vec_tables(self) -> None:
        dim = self.embedding_dim
        await self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS observations_vec USING vec0(
                observation_id INTEGER PRIMARY KEY,
                embedding float[{dim}] distance_metric=cosine
            );
        """)
        await self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_vec USING vec0(
                fact_id INTEGER PRIMARY KEY,
                embedding float[{dim}] distance_metric=cosine
            );
        """)

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
        await self._init_vec_tables()
        await self._set_meta("embedding_dim", str(new_dim))
        await self.conn.commit()
