from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.lens_pass import LensPass
from ntrp.memory.store.base import GraphDatabase

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite

TEST_EMBEDDING_DIM = 8

LENS_FILE = """---
directory: thirdlayer engineers
entity_type: person
---
## Belongs
Engineers who work at thirdlayer.

## Profile shape
- Role
- What they own
"""


class _FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload)


@pytest_asyncio.fixture
async def conn(tmp_path: Path):
    db_conn = await database.connect(tmp_path / "memory.db", vec=True)
    await db_conn.execute("PRAGMA foreign_keys=ON")
    db = GraphDatabase(db_conn, TEST_EMBEDDING_DIM)
    await db.init_schema()
    try:
        yield db_conn
    finally:
        await db_conn.close()


def _lens_dir(tmp_path: Path) -> Path:
    d = tmp_path / "lenses"
    d.mkdir()
    (d / "thirdlayer-engineers.md").write_text(LENS_FILE, encoding="utf-8")
    return d


async def _obs(repo: MemoryItemsRepository, content: str) -> str:
    return await repo.insert_item(
        MemoryItemInsert(content=content, source_refs=[], confidence=0.7, kind="observation", provenance="inferred")
    )


@pytest.mark.asyncio
async def test_lens_pass_materializes_directory_entity_and_edges(conn: aiosqlite.Connection, tmp_path: Path):
    repo = MemoryItemsRepository(conn)
    obs_id = await _obs(repo, "Kevin is a backend engineer at thirdlayer who owns the billing service.")

    fake = _FakeLLM(
        {"entities": [{"name": "Kevin", "profile": "Backend engineer; owns billing.", "source_ids": [obs_id]}]}
    )
    result = await LensPass(repo=repo, client=fake, lenses_dir=_lens_dir(tmp_path)).run()

    assert result.lenses == 1
    assert result.directories == 1
    assert result.entities_written == 1

    directories = await repo.list_directories()
    assert len(directories) == 1
    directory = directories[0]
    assert directory.title == "thirdlayer engineers"
    assert "lens:thirdlayer-engineers" in directory.tags

    members = await repo.list_directory_members(directory.id)
    assert [m.title for m in members] == ["Kevin"]
    assert members[0].kind == "entity"

    # evidence edge entity -> observation
    parents = await repo.list_parent_edges(members[0].id)
    roles = {(p.role, p.parent_id) for p in parents}
    assert ("member_of", directory.id) in roles
    assert ("evidence", obs_id) in roles


@pytest.mark.asyncio
async def test_lens_pass_is_idempotent(conn: aiosqlite.Connection, tmp_path: Path):
    repo = MemoryItemsRepository(conn)
    obs_id = await _obs(repo, "Kevin works at thirdlayer.")
    fake = _FakeLLM({"entities": [{"name": "Kevin", "profile": "Engineer.", "source_ids": [obs_id]}]})
    lens_dir = _lens_dir(tmp_path)

    await LensPass(repo=repo, client=fake, lenses_dir=lens_dir).run()
    await LensPass(repo=repo, client=fake, lenses_dir=lens_dir).run()

    assert len(await repo.list_directories()) == 1
    directory = (await repo.list_directories())[0]
    members = await repo.list_directory_members(directory.id)
    assert len(members) == 1  # no duplicate entity, no duplicate member_of edge


@pytest.mark.asyncio
async def test_lens_pass_ignores_unknown_source_ids(conn: aiosqlite.Connection, tmp_path: Path):
    repo = MemoryItemsRepository(conn)
    await _obs(repo, "Kevin works at thirdlayer.")
    fake = _FakeLLM({"entities": [{"name": "Kevin", "profile": "Engineer.", "source_ids": ["does-not-exist"]}]})
    await LensPass(repo=repo, client=fake, lenses_dir=_lens_dir(tmp_path)).run()

    directory = (await repo.list_directories())[0]
    entity = (await repo.list_directory_members(directory.id))[0]
    parents = await repo.list_parent_edges(entity.id)
    # only the member_of edge survives; the bogus evidence id is dropped
    assert {p.role for p in parents} == {"member_of"}
