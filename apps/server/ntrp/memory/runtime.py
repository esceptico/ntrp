"""Memory database holder for the memory_items pipeline."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self, TypedDict

import ntrp.database as database
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.logging import get_logger
from ntrp.memory.items_store import MemoryItemsRepository
from ntrp.memory.store.base import GraphDatabase

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite

_logger = get_logger(__name__)


class ReembedProgress(TypedDict):
    total: int
    done: int


class MemoryDatabase:
    def __init__(
        self,
        *,
        conn: aiosqlite.Connection,
        db: GraphDatabase,
        embedder: Embedder,
        model: str,
    ):
        self.conn = conn
        self.db = db
        self.embedder = embedder
        self._model = model
        self._reembed_task: asyncio.Task[None] | None = None
        self._reembed_progress: ReembedProgress | None = None
        self.items = MemoryItemsRepository(conn)

    @classmethod
    async def create(
        cls,
        *,
        db_path: Path | str,
        embedding: EmbeddingConfig,
        model: str,
    ) -> Self:
        conn = await database.connect(db_path, vec=True)
        embedder = Embedder(embedding)
        dim = int(embedder.config.dim)
        db = GraphDatabase(conn, dim)
        await db.init_schema()
        return cls(conn=conn, db=db, embedder=embedder, model=model)

    @property
    def model(self) -> str:
        return self._model

    def update_model(self, model: str) -> None:
        self._model = model

    @property
    def reembed_running(self) -> bool:
        return self._reembed_task is not None and not self._reembed_task.done()

    @property
    def reembed_progress(self) -> ReembedProgress | None:
        return self._reembed_progress

    def start_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False) -> None:
        if self.reembed_running:
            _logger.warning("Reembed already running; ignoring start request")
            return
        self._reembed_progress = {"total": 0, "done": 0}
        self._reembed_task = asyncio.create_task(self._run_reembed(embedding, rebuild=rebuild))

    async def _run_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool, batch_size: int = 100) -> None:
        try:
            new_embedder = Embedder(embedding)
            new_dim = int(new_embedder.config.dim)
            if rebuild:
                await self.db.rebuild_vec_tables(new_dim)

            cursor = await self.conn.execute(
                "SELECT id, content FROM memory_items WHERE status != 'archived'"
            )
            rows = await cursor.fetchall()
            total = len(rows)
            self._reembed_progress = {"total": total, "done": 0}

            from ntrp.database import serialize_embedding

            for i in range(0, total, batch_size):
                batch = rows[i : i + batch_size]
                texts = [r[1] for r in batch]
                if not texts:
                    continue
                embeddings = await new_embedder.embed(texts)
                for (row_id, _), emb in zip(batch, embeddings, strict=False):
                    blob = serialize_embedding(emb)
                    await self.conn.execute(
                        "INSERT OR REPLACE INTO memory_items_vec(item_id, embedding) VALUES (?, ?)",
                        (row_id, blob),
                    )
                await self.conn.commit()
                self._reembed_progress = {"total": total, "done": min(i + batch_size, total)}

            self.embedder = new_embedder
            _logger.info("Reembed complete: %d memory_items", total)
        finally:
            self._reembed_task = None

    async def close(self) -> None:
        if self._reembed_task is not None and not self._reembed_task.done():
            self._reembed_task.cancel()
        await self.conn.close()

    async def clear(self) -> None:
        """Wipe memory tables. Intended for tests."""
        await self.db.clear_all()
