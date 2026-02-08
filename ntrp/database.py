from pathlib import Path

import aiosqlite
import numpy as np
import sqlite_vec


def serialize_embedding(embedding: np.ndarray | list[float] | None) -> bytes | None:
    if embedding is None:
        return None
    arr = embedding if isinstance(embedding, np.ndarray) else np.array(embedding)
    return arr.astype(np.float32).tobytes()


def deserialize_embedding(data: bytes | None) -> np.ndarray | None:
    if data is None:
        return None
    arr = np.frombuffer(data, dtype=np.float32).copy()
    norm = np.linalg.norm(arr)
    return arr / norm if norm > 0 else arr


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA busy_timeout=30000;")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn


class VectorDatabase(Database):
    async def connect(self) -> None:
        await super().connect()
        await self.conn.enable_load_extension(True)
        await self.conn.load_extension(sqlite_vec.loadable_path())
        await self.conn.enable_load_extension(False)


class BaseRepository:
    def __init__(self, conn: aiosqlite.Connection, auto_commit: bool = True):
        self._conn = conn
        self._auto_commit = auto_commit

    @property
    def conn(self) -> aiosqlite.Connection:
        return self._conn

    async def _commit(self) -> None:
        if self._auto_commit:
            await self._conn.commit()

    async def commit(self) -> None:
        await self._conn.commit()
