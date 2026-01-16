import asyncio
import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio

from ntrp.memory.store.base import GraphDatabase

TEST_EMBEDDING_DIM = 768


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[GraphDatabase]:
    db_path = tmp_path / "test_memory.db"
    db = GraphDatabase(db_path, TEST_EMBEDDING_DIM)
    await db.connect()
    yield db
    await db.close()


def mock_embedding(text: str) -> np.ndarray:
    h = hashlib.md5(text.encode()).hexdigest()
    # MD5 is 32 chars, repeat to get TEST_EMBEDDING_DIM
    arr = np.array([int(c, 16) / 15.0 for c in h] * (TEST_EMBEDDING_DIM // 32))
    norm = np.linalg.norm(arr)
    return arr / norm if norm > 0 else arr
