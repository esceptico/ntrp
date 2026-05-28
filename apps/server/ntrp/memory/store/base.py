"""Memory database schema + GraphDatabase initializer.

After the legacy purge, the live schema is just `memory_items` (+ fts /
vec helpers), `memory_item_parents`, `episode_buffers`, and `meta`.
"""

import sqlite3

import aiosqlite

from ntrp.logging import get_logger

_logger = get_logger(__name__)

MEMORY_ITEMS_SCHEMA_VERSION = 32

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS memory_items (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN (
                        'episode', 'observation', 'claim',
                        'skill', 'proposal', 'artifact_ref'
                    )),
    content         TEXT NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN (
                        'recorded', 'inferred', 'user_authored', 'external'
                    )),
    source_refs     TEXT NOT NULL DEFAULT '[]',
    confidence      REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                        'active', 'superseded', 'archived'
                    )),
    valid_from      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invalid_at      TIMESTAMP,
    scope           TEXT NOT NULL DEFAULT 'user',
    tags            TEXT NOT NULL DEFAULT '[]',
    artifact_ref    TEXT,
    usage           TEXT NOT NULL DEFAULT '{"activated":0,"helped":0,"hurt":0,"ignored":0}',
    feedback        TEXT NOT NULL DEFAULT '{"thumbs_up":0,"thumbs_down":0,"corrections":0}',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_items_status_scope_kind ON memory_items(status, scope, kind);
CREATE INDEX IF NOT EXISTS idx_memory_items_valid_from ON memory_items(valid_from);
CREATE INDEX IF NOT EXISTS idx_memory_items_invalid_at ON memory_items(invalid_at);
CREATE INDEX IF NOT EXISTS idx_memory_items_updated_at ON memory_items(updated_at);

CREATE TABLE IF NOT EXISTS memory_item_parents (
    child_id    TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    parent_id   TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN (
                    'step', 'evidence', 'contradicts',
                    'supersedes', 'similar_to'
                )),
    "order"     INTEGER,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (child_id, parent_id, role)
);
CREATE INDEX IF NOT EXISTS idx_mip_child ON memory_item_parents(child_id);
CREATE INDEX IF NOT EXISTS idx_mip_parent ON memory_item_parents(parent_id);
CREATE INDEX IF NOT EXISTS idx_mip_role ON memory_item_parents(role);

CREATE TABLE IF NOT EXISTS episode_buffers (
    id                      TEXT PRIMARY KEY,
    scope                   TEXT NOT NULL,
    source_kind             TEXT NOT NULL,
    started_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    turn_count              INTEGER NOT NULL DEFAULT 0,
    tokens                  INTEGER NOT NULL DEFAULT 0,
    content_so_far          TEXT NOT NULL DEFAULT '',
    source_refs_so_far      TEXT NOT NULL DEFAULT '[]',
    running_centroid_vec    BLOB,
    closed_at               TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_episode_buffers_open_per_scope
    ON episode_buffers(scope, source_kind)
    WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_episode_buffers_last_activity ON episode_buffers(last_activity_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
    item_id UNINDEXED,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
    INSERT INTO memory_items_fts(item_id, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
    DELETE FROM memory_items_fts WHERE item_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
    DELETE FROM memory_items_fts WHERE item_id = old.id;
    INSERT INTO memory_items_fts(item_id, content) VALUES (new.id, new.content);
END;
"""


class GraphDatabase:
    def __init__(self, conn: aiosqlite.Connection, embedding_dim: int):
        self.conn = conn
        self.embedding_dim = embedding_dim
        self.dim_changed = False

    async def init_schema(self) -> None:
        await self.conn.executescript(SCHEMA)
        await self._init_vec_table()

        stored_dim = await self._get_meta("embedding_dim")
        if stored_dim is None or int(stored_dim) != self.embedding_dim:
            _logger.info(
                "Rebuilding memory vec table (stored=%s, current=%d)",
                stored_dim,
                self.embedding_dim,
            )
            await self.rebuild_vec_tables(self.embedding_dim)
            self.dim_changed = True

        await self._set_meta("schema_version", str(MEMORY_ITEMS_SCHEMA_VERSION))
        await self._set_meta("embedding_dim", str(self.embedding_dim))
        await self.conn.commit()

    async def clear_all(self) -> None:
        await self.conn.execute("DELETE FROM memory_item_parents")
        await self.conn.execute("DELETE FROM memory_items")
        await self.conn.execute("DELETE FROM episode_buffers")
        try:
            await self.conn.execute("DELETE FROM memory_items_vec")
        except sqlite3.OperationalError:
            pass
        await self.conn.commit()

    async def _init_vec_table(self) -> None:
        rows = await self.conn.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memory_items_vec'"
        )
        if rows:
            return
        try:
            await self.conn.execute(
                f"""
                CREATE VIRTUAL TABLE memory_items_vec USING vec0(
                    item_id TEXT PRIMARY KEY,
                    embedding float[{self.embedding_dim}] distance_metric=cosine
                );
                """
            )
        except sqlite3.OperationalError as exc:
            if "no such module: vec0" in str(exc):
                _logger.warning("sqlite-vec extension unavailable; memory_items_vec skipped")
                return
            raise

    async def rebuild_vec_tables(self, new_dim: int) -> None:
        self.embedding_dim = new_dim
        await self.conn.execute("DROP TABLE IF EXISTS memory_items_vec")
        await self._init_vec_table()
        await self._set_meta("embedding_dim", str(new_dim))
        await self.conn.commit()

    async def _get_meta(self, key: str) -> str | None:
        try:
            rows = await self.conn.execute_fetchall("SELECT value FROM meta WHERE key = ?", (key,))
            return rows[0][0] if rows else None
        except Exception:
            return None

    async def _set_meta(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )
