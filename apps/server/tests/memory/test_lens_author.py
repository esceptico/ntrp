from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.activation import MemoryActivationBundle
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.lens_author import LensAuthor, LensAuthorError, LensSpec, render_lens_markdown
from ntrp.memory.lens_pass import LensPass
from ntrp.memory.store.base import GraphDatabase

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite

TEST_EMBEDDING_DIM = 8

pytestmark = pytest.mark.asyncio


class _FakeClient:
    """Returns a fixed JSON payload regardless of prompt."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload)


class _FakeRetrieval:
    async def search(self, request, *, now=None) -> MemoryActivationBundle:
        return MemoryActivationBundle(
            query=request.query, scope=request.scope, kinds=None,
            candidates=[], used_chars=0, prompt_context="", skills_to_use=[],
        )


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


def _spec_payload() -> dict:
    return {
        "slug": "Northwind Engineers!",  # exercises slug normalization
        "directory": "Northwind engineers",
        "entity_type": "person",
        "belongs": "Engineers at Northwind. Exclude PMs.",
        "profile_shape": ["Role", "What they own"],
    }


def _author(conn, tmp_path: Path, *, spec=None, extract=None) -> tuple[LensAuthor, _FakeClient]:
    repo = MemoryItemsRepository(conn)
    lenses_dir = tmp_path / "lenses"
    lens_pass = LensPass(
        repo=repo,
        client=_FakeClient(extract or {"entities": []}),
        lenses_dir=lenses_dir,
    )
    author_client = _FakeClient(spec or _spec_payload())
    author = LensAuthor(
        repo=repo, retrieval=_FakeRetrieval(), lens_pass=lens_pass,
        client=author_client, lenses_dir=lenses_dir,
    )
    return author, author_client


async def test_render_lens_markdown_roundtrips_frontmatter():
    spec = LensSpec.model_validate(_spec_payload())
    md = render_lens_markdown(spec)
    assert md.startswith("---\ndirectory: Northwind engineers\nentity_type: person\n---\n")
    assert "## Belongs" in md and "## Profile shape" in md and "- Role" in md


async def test_propose_creates_open_proposal_with_normalized_slug(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    proposal = await author.propose("group the engineers by company")

    assert proposal.slug == "northwind-engineers"  # spaces/punctuation stripped
    assert proposal.directory == "Northwind engineers"

    repo = MemoryItemsRepository(conn)
    item = await repo.get_item(proposal.proposal_id)
    assert item.kind == "proposal"
    assert "lens-proposal" in item.tags
    assert "proposal-status:open" in item.tags
    assert "lens:northwind-engineers" in item.tags
    assert item.content.startswith("---\ndirectory: Northwind engineers")
    # confidence is computed (no grounding candidates here), never the old 0.6 literal
    expected = compute_confidence(
        provenance="inferred",
        parent_confidences=[],
        contradiction_count=0,
        age_days=0,
        last_used_days=0,
        helped=0,
        hurt=0,
        ignored=0,
    )
    assert item.confidence == pytest.approx(expected)
    assert item.confidence != 0.6

    listed = await author.list_proposals()
    assert [p["proposal_id"] for p in listed] == [proposal.proposal_id]


async def test_approve_writes_lens_file_runs_pass_and_closes_proposal(conn: aiosqlite.Connection, tmp_path: Path):
    repo = MemoryItemsRepository(conn)
    obs_id = await repo.insert_item(
        MemoryItemInsert(content="Kevin is a backend engineer at Northwind.", source_refs=[],
                         confidence=0.7, kind="observation", provenance="inferred")
    )
    author, _ = _author(
        conn, tmp_path,
        extract={"entities": [{"name": "Kevin", "profile": "Backend engineer.", "source_ids": [obs_id]}]},
    )
    proposal = await author.propose("engineers by company")

    result = await author.approve(proposal.proposal_id)

    assert result["slug"] == "northwind-engineers"
    assert (tmp_path / "lenses" / "northwind-engineers.md").exists()
    assert result["run"]["directories"] == 1
    assert result["run"]["entities_written"] == 1

    directories = await repo.list_directories()
    assert [d.title for d in directories] == ["Northwind engineers"]
    members = await repo.list_directory_members(directories[0].id)
    assert [m.title for m in members] == ["Kevin"]

    # proposal is no longer open
    assert await author.list_proposals() == []


async def test_approve_unknown_proposal_raises(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    with pytest.raises(LensAuthorError):
        await author.approve("does-not-exist")


async def test_reject_archives_proposal(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    proposal = await author.propose("engineers")
    await author.reject(proposal.proposal_id)

    assert await author.list_proposals() == []
    repo = MemoryItemsRepository(conn)
    item = await repo.get_item(proposal.proposal_id)
    assert item.status == "archived"


async def test_propose_empty_query_raises(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    with pytest.raises(LensAuthorError):
        await author.propose("   ")


async def test_update_lens_rewrites_file_and_reruns(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    proposal = await author.propose("engineers")
    await author.approve(proposal.proposal_id)

    new_md = "---\ndirectory: Northwind engineers\nentity_type: person\n---\n## Belongs\nOnly backend engineers.\n"
    result = await author.update_lens("northwind-engineers", new_md)

    assert result["slug"] == "northwind-engineers"
    assert (tmp_path / "lenses" / "northwind-engineers.md").read_text() == new_md


async def test_update_lens_unknown_raises(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    with pytest.raises(LensAuthorError):
        await author.update_lens("does-not-exist", "---\ndirectory: X\nentity_type: person\n---\n## Belongs\nx\n")


async def test_update_lens_invalid_markdown_raises(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    proposal = await author.propose("engineers")
    await author.approve(proposal.proposal_id)
    with pytest.raises(LensAuthorError):
        await author.update_lens("northwind-engineers", "no frontmatter here")


async def test_delete_lens_removes_file_directory_and_entities(conn: aiosqlite.Connection, tmp_path: Path):
    repo = MemoryItemsRepository(conn)
    obs_id = await repo.insert_item(
        MemoryItemInsert(content="Kevin is a backend engineer at Northwind.", source_refs=[],
                         confidence=0.7, kind="observation", provenance="inferred")
    )
    author, _ = _author(
        conn, tmp_path,
        extract={"entities": [{"name": "Kevin", "profile": "Backend engineer.", "source_ids": [obs_id]}]},
    )
    proposal = await author.propose("engineers by company")
    await author.approve(proposal.proposal_id)

    result = await author.delete_lens("northwind-engineers")

    assert result["file_removed"] is True
    assert result["directory_removed"] is True
    assert result["entities_removed"] == 1
    assert not (tmp_path / "lenses" / "northwind-engineers.md").exists()
    assert await repo.list_directories() == []
    # source observation is untouched
    assert await repo.get_item(obs_id) is not None


async def test_delete_lens_missing_is_noop(conn: aiosqlite.Connection, tmp_path: Path):
    author, _ = _author(conn, tmp_path)
    result = await author.delete_lens("never-existed")
    assert result["file_removed"] is False
    assert result["directory_removed"] is False
    assert result["entities_removed"] == 0
