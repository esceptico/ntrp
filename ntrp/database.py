from pathlib import Path

import aiosqlite
import numpy as np
import sqlite_vec


def serialize_embedding(embedding: np.ndarray | list[float] | None) -> bytes | None:
    if embedding is None:
        return None
    arr = embedding if isinstance(embedding, np.ndarray) else np.array(embedding)
    arr = arr.astype(np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tobytes()


def deserialize_embedding(data: bytes | None) -> np.ndarray | None:
    if data is None:
        return None
    return np.frombuffer(data, dtype=np.float32).copy()


async def connect(db_path: Path, *, vec: bool = False) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA synchronous=NORMAL;")
    await conn.execute("PRAGMA busy_timeout=30000;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    if vec:
        await conn.enable_load_extension(True)
        await conn.load_extension(sqlite_vec.loadable_path())
        await conn.enable_load_extension(False)
    return conn
