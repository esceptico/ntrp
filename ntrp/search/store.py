import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite
import sqlite_vec

from ntrp.logging import get_logger

logger = get_logger(__name__)

SNIPPET_DISPLAY_LIMIT = 500


@dataclass
class Item:
    id: int
    source: str
    source_id: str
    title: str
    content: str | None
    snippet: str | None
    content_hash: str
    embedding: bytes | None
    metadata: dict | None
    indexed_at: str


class SearchStore:
    def __init__(self, db_path: Path, embedding_dim: int):
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self._conn: aiosqlite.Connection | None = None
        self._has_fts = False
        self._has_vec = False

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        # Load sqlite_vec extension
        await self._conn.enable_load_extension(True)
        await self._conn.load_extension(sqlite_vec.loadable_path())
        await self._conn.enable_load_extension(False)

        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA busy_timeout=30000;")

        await self._check_integrity()
        await self._init_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SearchStore not connected")
        return self._conn

    async def _check_integrity(self) -> None:
        try:
            rows = await self.conn.execute_fetchall("PRAGMA integrity_check;")
            if not rows or rows[0][0] != "ok":
                raise RuntimeError("Integrity check failed")
        except Exception:
            await self.conn.close()
            self.db_path.unlink(missing_ok=True)
            Path(str(self.db_path) + "-wal").unlink(missing_ok=True)
            Path(str(self.db_path) + "-shm").unlink(missing_ok=True)

            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row

            await self._conn.enable_load_extension(True)
            await self._conn.load_extension(sqlite_vec.loadable_path())
            await self._conn.enable_load_extension(False)

            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA synchronous=NORMAL;")
            await self._conn.execute("PRAGMA busy_timeout=30000;")

    async def _init_schema(self) -> None:
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT,
                content TEXT,
                snippet TEXT,
                content_hash TEXT,
                metadata TEXT,
                indexed_at TEXT,
                UNIQUE(source, source_id)
            );

            CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
            CREATE INDEX IF NOT EXISTS idx_items_hash ON items(source, content_hash);
        """)

        try:
            await self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
                    title, content,
                    content='items',
                    content_rowid='id'
                );
            """)
            await self.conn.executescript("""
                CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
                    INSERT INTO items_fts(rowid, title, content)
                    VALUES (new.id, new.title, new.content);
                END;

                CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
                    INSERT INTO items_fts(items_fts, rowid, title, content)
                    VALUES ('delete', old.id, old.title, old.content);
                END;

                CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
                    INSERT INTO items_fts(items_fts, rowid, title, content)
                    VALUES ('delete', old.id, old.title, old.content);
                    INSERT INTO items_fts(rowid, title, content)
                    VALUES (new.id, new.title, new.content);
                END;
            """)
            self._has_fts = True
        except Exception:
            self._has_fts = False

        try:
            await self.conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS items_vec USING vec0(
                    item_id INTEGER PRIMARY KEY,
                    embedding float[{self.embedding_dim}] distance_metric=cosine
                );
            """)
            self._has_vec = True
        except Exception as e:
            logger.warning("Failed to create vec0 table: %s", e)
            self._has_vec = False

        await self.conn.commit()

    @property
    def has_fts(self) -> bool:
        return self._has_fts

    @property
    def has_vec(self) -> bool:
        return self._has_vec

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()

    @staticmethod
    def make_snippet(content: str) -> str:
        return content.replace("\n", " ").strip()[:SNIPPET_DISPLAY_LIMIT]

    async def get_by_id(self, row_id: int) -> Item | None:
        rows = await self.conn.execute_fetchall(
            """SELECT id, source, source_id, title, content, snippet,
                      content_hash, metadata, indexed_at
               FROM items WHERE id = ?""",
            (row_id,),
        )
        if not rows:
            return None

        row = rows[0]
        return Item(
            id=row["id"],
            source=row["source"],
            source_id=row["source_id"],
            title=row["title"] or "",
            content=row["content"],
            snippet=row["snippet"],
            content_hash=row["content_hash"],
            embedding=None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            indexed_at=row["indexed_at"],
        )

    async def exists_with_hash(self, source: str, source_id: str, content_hash: str) -> bool:
        rows = await self.conn.execute_fetchall(
            "SELECT content_hash FROM items WHERE source = ? AND source_id = ?",
            (source, source_id),
        )
        return bool(rows) and rows[0]["content_hash"] == content_hash

    async def get_indexed_hashes(self, source: str) -> dict[str, tuple[int, str]]:
        rows = await self.conn.execute_fetchall(
            "SELECT id, source_id, content_hash FROM items WHERE source = ?", (source,)
        )
        return {row["source_id"]: (row["id"], row["content_hash"]) for row in rows}

    async def upsert(
        self,
        source: str,
        source_id: str,
        title: str,
        content: str,
        embedding: bytes,
        metadata: dict | None = None,
    ) -> bool:
        content_hash = self.hash_content(content)
        snippet = self.make_snippet(content)
        now = datetime.now().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None

        existing = await self.conn.execute_fetchall(
            "SELECT id, content_hash FROM items WHERE source = ? AND source_id = ?",
            (source, source_id),
        )

        if existing and existing[0]["content_hash"] == content_hash:
            return False

        if existing:
            item_id = existing[0]["id"]
            await self.conn.execute(
                """
                UPDATE items
                SET title = ?, content = ?, snippet = ?, content_hash = ?,
                    metadata = ?, indexed_at = ?
                WHERE id = ?
                """,
                (title, content, snippet, content_hash, metadata_json, now, item_id),
            )
            if self._has_vec:
                await self.conn.execute("DELETE FROM items_vec WHERE item_id = ?", (item_id,))
                await self.conn.execute(
                    "INSERT INTO items_vec(item_id, embedding) VALUES (?, ?)",
                    (item_id, embedding),
                )
        else:
            cursor = await self.conn.execute(
                """
                INSERT INTO items (source, source_id, title, content, snippet, content_hash,
                                   metadata, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source, source_id, title, content, snippet, content_hash, metadata_json, now),
            )
            item_id = cursor.lastrowid
            if self._has_vec:
                await self.conn.execute(
                    "INSERT INTO items_vec(item_id, embedding) VALUES (?, ?)",
                    (item_id, embedding),
                )

        await self.conn.commit()
        return True

    async def delete(self, source: str, source_id: str) -> bool:
        rows = await self.conn.execute_fetchall(
            "SELECT id FROM items WHERE source = ? AND source_id = ?",
            (source, source_id),
        )
        if not rows:
            return False

        item_id = rows[0]["id"]

        if self._has_vec:
            await self.conn.execute("DELETE FROM items_vec WHERE item_id = ?", (item_id,))

        await self.conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        await self.conn.commit()
        return True

    async def clear_source(self, source: str) -> int:
        rows = await self.conn.execute_fetchall("SELECT id FROM items WHERE source = ?", (source,))
        if not rows:
            return 0

        item_ids = [row["id"] for row in rows]

        if self._has_vec:
            placeholders = ",".join("?" * len(item_ids))
            await self.conn.execute(
                f"DELETE FROM items_vec WHERE item_id IN ({placeholders})",
                item_ids,
            )

        cursor = await self.conn.execute("DELETE FROM items WHERE source = ?", (source,))
        await self.conn.commit()
        return cursor.rowcount

    async def get_stats(self) -> dict[str, int]:
        rows = await self.conn.execute_fetchall("SELECT source, COUNT(*) as cnt FROM items GROUP BY source")
        return {row["source"]: row["cnt"] for row in rows}

    async def clear_all(self) -> int:
        if self._has_vec:
            await self.conn.execute("DELETE FROM items_vec")
        cursor = await self.conn.execute("DELETE FROM items")
        await self.conn.commit()
        return cursor.rowcount

    async def vector_search(
        self,
        query_embedding: bytes,
        sources: list[str] | None = None,
        limit: int = 20,
    ) -> list[tuple[int, float]]:
        if not self._has_vec:
            return []

        try:
            if sources:
                placeholders = ",".join("?" * len(sources))
                rows = await self.conn.execute_fetchall(
                    f"""
                    SELECT v.item_id, v.distance
                    FROM items_vec v
                    JOIN items i ON v.item_id = i.id
                    WHERE v.embedding MATCH ? AND k = ?
                      AND i.source IN ({placeholders})
                    ORDER BY v.distance
                    """,
                    [query_embedding, limit * 2, *sources],
                )
            else:
                rows = await self.conn.execute_fetchall(
                    """
                    SELECT item_id, distance
                    FROM items_vec
                    WHERE embedding MATCH ? AND k = ?
                    ORDER BY distance
                    """,
                    (query_embedding, limit * 2),
                )

            return [(row[0], 1 - row[1]) for row in rows]
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []

    async def fts_search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 20,
    ) -> list[tuple[int, float]]:
        if not self._has_fts:
            return []

        terms = query.split()
        escaped_terms = [f'"{t.replace(chr(34), chr(34) + chr(34))}"' for t in terms]
        fts_query = " ".join(escaped_terms)

        try:
            if sources:
                placeholders = ",".join("?" * len(sources))
                rows = await self.conn.execute_fetchall(
                    f"""
                    SELECT items.id, bm25(items_fts) as score
                    FROM items_fts
                    JOIN items ON items_fts.rowid = items.id
                    WHERE items_fts MATCH ? AND items.source IN ({placeholders})
                    ORDER BY score
                    LIMIT ?
                    """,
                    [fts_query, *sources, limit],
                )
            else:
                rows = await self.conn.execute_fetchall(
                    """
                    SELECT items.id, bm25(items_fts) as score
                    FROM items_fts
                    JOIN items ON items_fts.rowid = items.id
                    WHERE items_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, limit),
                )

            return [(row[0], -row[1]) for row in rows]
        except Exception as e:
            logger.warning("FTS search failed for query '%s': %s", query, e)
            return []
