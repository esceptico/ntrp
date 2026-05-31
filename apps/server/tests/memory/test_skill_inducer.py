from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.connectors._confidence import compute_confidence
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.skill_inducer import (
    IsToolableGate,
    SkillInducer,
    _slugify,
)
from ntrp.memory.store.base import GraphDatabase

if TYPE_CHECKING:
    import aiosqlite

TEST_EMBEDDING_DIM = 8
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
SKILL_BODY = """# PR Triage

## When to use
Use this when morning PR triage starts.

## Steps
1. Check the pull request list.
2. Assign reviewers by touched file paths.

## Inputs
- Pull request list

## Outputs
- Review assignments

## Notes
Keep the workflow grounded in runtime evidence.
"""


class _FakeLLM:
    def __init__(self, *responses: str):
        self.responses = list(responses) or ["morning PR triage"]
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if len(self.responses) == 1:
            return self.responses[0]
        return self.responses.pop(0)


class _FakeEmbedder:
    def __init__(self):
        self.calls: list[str] = []

    async def embed_one(self, text: str) -> np.ndarray:
        self.calls.append(text)
        return _vec(0)


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


def _vec(index: int) -> np.ndarray:
    vector = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    vector[index] = 1.0
    return vector


def _cos_vec(cosine: float) -> np.ndarray:
    vector = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    vector[0] = cosine
    vector[1] = math.sqrt(1.0 - cosine * cosine)
    return vector


async def _insert_item(
    conn: aiosqlite.Connection,
    content: str,
    *,
    kind: str = "claim",
    tags: list[str] | None = None,
    embedding: np.ndarray | None = None,
    scope: str = "user",
    valid_from: datetime = NOW,
    status: str = "active",
    source_refs: list[dict] | None = None,
) -> str:
    return await MemoryItemsRepository(conn).insert_item(
        MemoryItemInsert(
            kind=kind,
            content=content,
            provenance="inferred",
            source_refs=source_refs or [{"kind": "test", "ref": content}],
            confidence=0.7,
            status=status,
            scope=scope,
            tags=tags or [],
            embedding=embedding if embedding is not None else _vec(0),
            valid_from=valid_from,
        )
    )


async def _claim_with_evidence(
    conn: aiosqlite.Connection,
    *,
    claim_text: str = "User triages pull requests every morning.",
    evidence_count: int = 3,
    tags: list[str] | None = None,
) -> str:
    repo = MemoryItemsRepository(conn)
    claim_id = await _insert_item(conn, claim_text, tags=tags or ["triage"])
    for index in range(evidence_count):
        evidence_id = await _insert_item(
            conn,
            f"evidence {index}",
            kind="observation",
            tags=tags or ["triage"],
            embedding=_cos_vec(0.9),
            valid_from=NOW - timedelta(minutes=index + 1),
        )
        await repo.insert_parent_edge(claim_id, evidence_id, "evidence")
    return claim_id


async def _row(conn: aiosqlite.Connection, item_id: str) -> aiosqlite.Row:
    rows = await conn.execute_fetchall("SELECT * FROM memory_items WHERE id = ?", (item_id,))
    assert rows
    return rows[0]


async def _rows(conn: aiosqlite.Connection, *, kind: str) -> list[aiosqlite.Row]:
    return await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind = ? ORDER BY created_at, id", (kind,))


def test_slugify_is_ascii_bounded_and_hyphenated():
    assert _slugify("Morning PR triage!!! / déjà vu with a very long tail") == "morning-pr-triage-deja-vu-with-a-very-lo"


@pytest.mark.asyncio
async def test_gate_rejects_unsourced_claim_without_calling_trigger_judge(conn: aiosqlite.Connection):
    claim_id = await _claim_with_evidence(conn, evidence_count=2)
    judge = _FakeLLM("morning PR triage")

    result = await IsToolableGate(repo=MemoryItemsRepository(conn), judge_client=judge).evaluate_and_tag(claim_id)

    assert result.is_toolable is False
    assert "only 2 supporting items" in result.reason
    assert judge.prompts == []
    assert "toolable:false" in json.loads((await _row(conn, claim_id))["tags"])


@pytest.mark.asyncio
async def test_gate_tags_toolable_claim_and_trigger(conn: aiosqlite.Connection):
    claim_id = await _claim_with_evidence(conn, evidence_count=3)
    judge = _FakeLLM("morning PR triage")

    result = await IsToolableGate(repo=MemoryItemsRepository(conn), judge_client=judge).evaluate_and_tag(claim_id)

    tags = json.loads((await _row(conn, claim_id))["tags"])
    assert result.is_toolable is True
    assert "toolable:true" in tags
    assert "trigger:morning-pr-triage" in tags
    assert "User triages pull requests every morning." in judge.prompts[0]
    assert "evidence 0" in judge.prompts[0]


@pytest.mark.asyncio
async def test_gate_rejects_unclear_trigger(conn: aiosqlite.Connection):
    claim_id = await _claim_with_evidence(conn, evidence_count=3)

    result = await IsToolableGate(repo=MemoryItemsRepository(conn), judge_client=_FakeLLM("unclear")).evaluate_and_tag(
        claim_id
    )

    tags = json.loads((await _row(conn, claim_id))["tags"])
    assert result.is_toolable is False
    assert "no identifiable trigger" in result.reason
    assert "toolable:false" in tags
    assert not any(tag.startswith("trigger:") for tag in tags)


@pytest.mark.asyncio
async def test_gate_documents_stubbed_determinism_and_success_checks(conn: aiosqlite.Connection):
    claim_id = await _claim_with_evidence(conn, evidence_count=3)

    result = await IsToolableGate(repo=MemoryItemsRepository(conn), judge_client=_FakeLLM()).evaluate(claim_id)

    assert "determinism skipped" in result.reason
    assert "success signal skipped" in result.reason


@pytest.mark.asyncio
async def test_gate_trigger_prompt_caps_supporting_evidence_at_five_items(conn: aiosqlite.Connection):
    claim_id = await _claim_with_evidence(conn, evidence_count=7)
    judge = _FakeLLM("morning PR triage")

    await IsToolableGate(repo=MemoryItemsRepository(conn), judge_client=judge).evaluate_and_tag(claim_id)

    assert "evidence 0" in judge.prompts[0]
    assert "evidence 4" in judge.prompts[0]
    assert "evidence 5" not in judge.prompts[0]


@pytest.mark.asyncio
async def test_inducer_writes_proposal_file_row_and_derivation_edges(conn: aiosqlite.Connection, tmp_path: Path):
    claim_id = await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])
    draft_dir = tmp_path / "drafts"

    result = await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=draft_dir,
    ).run(now=NOW)

    proposals = await _rows(conn, kind="proposal")
    assert result.proposals_written == 1
    assert len(proposals) == 1
    assert (draft_dir / "pr-triage" / "SKILL.md").read_text() == SKILL_BODY
    assert {"proposal", "skill-draft", "proposal-status:open", "slug:pr-triage"} <= set(json.loads(proposals[0]["tags"]))
    edges = await MemoryItemsRepository(conn).list_parent_edges(proposals[0]["id"])
    assert [(edge.parent_id, edge.role) for edge in edges] == [(claim_id, "evidence")]
    # proposal confidence is derived from the source claim, never the old 0.5 literal
    expected = compute_confidence(
        provenance="inferred",
        parent_confidences=[0.7],
        contradiction_count=0,
        age_days=0,
        last_used_days=0,
        helped=0,
        hurt=0,
        ignored=0,
    )
    assert proposals[0]["confidence"] == pytest.approx(expected)
    assert proposals[0]["confidence"] != 0.5


@pytest.mark.asyncio
async def test_inducer_skips_claims_without_toolable_true_tag(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, tags=["trigger:morning-pr-triage"])

    result = await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    assert result.claims_considered == 1
    assert result.toolable_claims == 0
    assert result.proposals_written == 0


@pytest.mark.asyncio
async def test_inducer_skips_toolable_claims_without_trigger_tag(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, tags=["toolable:true"])

    result = await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    assert result.toolable_claims == 1
    assert result.clusters_found == 0
    assert result.proposals_written == 0


@pytest.mark.asyncio
async def test_inducer_skips_claim_with_existing_derived_proposal(conn: aiosqlite.Connection, tmp_path: Path):
    repo = MemoryItemsRepository(conn)
    claim_id = await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])
    proposal_id = await _insert_item(conn, "draft", kind="proposal", tags=["proposal-status:open"])
    await repo.insert_parent_edge(proposal_id, claim_id, "evidence")

    result = await SkillInducer(
        repo=repo,
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    assert result.proposals_written == 0
    assert len(await _rows(conn, kind="proposal")) == 1


@pytest.mark.asyncio
async def test_inducer_clusters_by_trigger_tag(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, claim_text="User triages PRs.", tags=["toolable:true", "trigger:morning-pr-triage"])
    await _claim_with_evidence(conn, claim_text="User assigns PR reviewers.", tags=["toolable:true", "trigger:morning-pr-triage"])

    result = await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    proposals = await _rows(conn, kind="proposal")
    edges = await MemoryItemsRepository(conn).list_parent_edges(proposals[0]["id"])
    assert result.clusters_found == 1
    assert result.proposals_written == 1
    assert len([edge for edge in edges if edge.role == "evidence"]) == 2


@pytest.mark.asyncio
async def test_inducer_writes_one_proposal_per_trigger(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, claim_text="User triages PRs.", tags=["toolable:true", "trigger:morning-pr-triage"])
    await _claim_with_evidence(conn, claim_text="User files notes.", tags=["toolable:true", "trigger:file-notes"])
    client = _FakeLLM(SKILL_BODY, SKILL_BODY.replace("PR Triage", "File Notes"))

    result = await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=client,
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    assert result.clusters_found == 2
    assert result.proposals_written == 2
    assert {json.loads(row["source_refs"])[0]["skill_slug"] for row in await _rows(conn, kind="proposal")} == {
        "pr-triage",
        "file-notes",
    }


@pytest.mark.asyncio
async def test_inducer_min_cluster_size_one_still_proposes(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])

    result = await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    assert result.clusters_found == 1
    assert result.proposals_written == 1


@pytest.mark.asyncio
async def test_inducer_adds_skill_title_when_draft_lacks_h1(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])

    await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM("## Steps\n1. Check PRs."),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    proposal = (await _rows(conn, kind="proposal"))[0]
    assert proposal["content"].startswith("# Morning PR Triage\n\n## Steps")
    assert "slug:morning-pr-triage" in json.loads(proposal["tags"])


@pytest.mark.asyncio
async def test_inducer_source_refs_include_proposal_and_source_claims(conn: aiosqlite.Connection, tmp_path: Path):
    claim_id = await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])

    await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    source_refs = json.loads((await _rows(conn, kind="proposal"))[0]["source_refs"])
    assert source_refs[0] == {
        "type": "proposal",
        "skill_slug": "pr-triage",
        "draft_path": str(tmp_path / "drafts" / "pr-triage" / "SKILL.md"),
    }
    assert {"type": "source_claim", "id": claim_id} in source_refs


@pytest.mark.asyncio
async def test_inducer_skill_prompt_contains_claims_and_supporting_items(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])
    client = _FakeLLM(SKILL_BODY)

    await SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=client,
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    ).run(now=NOW)

    assert "Trigger: morning-pr-triage" in client.prompts[0]
    assert "- User triages pull requests every morning." in client.prompts[0]
    assert "- evidence 0" in client.prompts[0]


@pytest.mark.asyncio
async def test_list_proposals_returns_open_status_and_source_count(conn: aiosqlite.Connection, tmp_path: Path):
    await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])
    inducer = SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    )
    await inducer.run(now=NOW)

    proposals = await inducer.list_proposals(status="open")

    assert proposals[0]["status"] == "open"
    assert proposals[0]["slug"] == "pr-triage"
    assert proposals[0]["source_claim_count"] == 1


@pytest.mark.asyncio
async def test_approve_proposal_rolls_back_skill_file_when_db_insert_fails(
    conn: aiosqlite.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])
    repo = MemoryItemsRepository(conn)
    inducer = SkillInducer(
        repo=repo,
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
        skills_dir=tmp_path / "skills",
    )
    await inducer.run(now=NOW)
    proposal = (await inducer.list_proposals(status="open"))[0]
    draft_path = Path(proposal["draft_path"])

    async def fail_insert(*args, **kwargs):
        raise RuntimeError("db insert failed")

    monkeypatch.setattr(repo, "insert_item", fail_insert)

    with pytest.raises(RuntimeError, match="db insert failed"):
        await inducer.approve_proposal(proposal["id"], now=NOW)

    assert draft_path.exists()
    assert not (tmp_path / "skills" / proposal["slug"] / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_run_removes_draft_file_when_proposal_insert_fails(
    conn: aiosqlite.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    await _claim_with_evidence(conn, tags=["toolable:true", "trigger:morning-pr-triage"])
    repo = MemoryItemsRepository(conn)
    inducer = SkillInducer(
        repo=repo,
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
    )

    async def fail_insert(*args, **kwargs):
        raise RuntimeError("db insert failed")

    monkeypatch.setattr(repo, "insert_item", fail_insert)

    with pytest.raises(RuntimeError, match="db insert failed"):
        await inducer.run(now=NOW)

    assert list((tmp_path / "drafts").glob("**/SKILL.md")) == []
