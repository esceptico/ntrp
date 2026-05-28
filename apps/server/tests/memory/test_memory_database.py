from pathlib import Path

import pytest

from ntrp.embedder import EmbeddingConfig
from ntrp.memory.runtime import MemoryDatabase

pytestmark = pytest.mark.asyncio


async def test_memory_database_create_uses_embedding_config_dim(tmp_path: Path):
    memory = await MemoryDatabase.create(
        db_path=tmp_path / "memory.db",
        embedding=EmbeddingConfig(model="test-embedding", dim=8),
        model="test-model",
    )
    try:
        assert memory.db.embedding_dim == 8
        assert memory.embedder.config.dim == 8

        rows = await memory.conn.execute_fetchall(
            "SELECT value FROM meta WHERE key = 'embedding_dim'"
        )
        assert rows[0]["value"] == "8"

        vec_rows = await memory.conn.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memory_items_vec'"
        )
        assert vec_rows
    finally:
        await memory.close()


async def test_memory_database_reembed_rebuild_uses_embedding_config_dim(tmp_path: Path):
    memory = await MemoryDatabase.create(
        db_path=tmp_path / "memory.db",
        embedding=EmbeddingConfig(model="test-embedding", dim=8),
        model="test-model",
    )
    try:
        await memory._run_reembed(
            EmbeddingConfig(model="test-embedding-v2", dim=16),
            rebuild=True,
        )

        assert memory.db.embedding_dim == 16
        assert memory.embedder.config.dim == 16
        rows = await memory.conn.execute_fetchall(
            "SELECT value FROM meta WHERE key = 'embedding_dim'"
        )
        assert rows[0]["value"] == "16"
    finally:
        await memory.close()
