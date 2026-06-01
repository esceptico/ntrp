"""Focused tests for the recall() memory tool (ntrp/tools/memory.py).

Tmp DB ONLY (never ~/.ntrp/memory.db). The Retriever runs over a real Stage-2
store with the offline FakeEmbedder; the small pool fits the token budget so
compression renders verbatim with ZERO LLM calls. We assert the tool's three
observable behaviors: structural scope resolution, the recalled bundle, and the
unavailable-service guard.
"""

import types
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory import (
    Kind,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
)
from ntrp.memory.pipeline.retrieve import Retriever
from ntrp.tools.memory import MEMORY_READ_SERVICE, RecallInput, recall
from tests.conftest import FakeEmbedder

pytestmark = pytest.mark.asyncio

USER = Scope(kind=ScopeKind.USER)
PROJECT = Scope(kind=ScopeKind.PROJECT, key="proj-1")


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db")  # tmp only
    from ntrp.memory.store import MemoryStore

    store = MemoryStore(conn)
    await store.init_schema()
    yield store
    await conn.close()


async def _add(store, content, scope, item_id):
    await store.create_item(
        MemoryItem(
            id=item_id,
            kind=Kind.CLAIM,
            content=content,
            scope=scope,
            provenance=Provenance.USER_AUTHORED,
        )
    )


def _vocab(*phrases: str) -> list[str]:
    seen: list[str] = []
    for p in phrases:
        for w in p.lower().split():
            if w not in seen:
                seen.append(w)
    return seen


def _execution(*, services: dict, project=None):
    """Minimal ToolExecution stand-in: recall() reads only ctx.services and
    ctx.project, so a namespace is sufficient and keeps the test offline."""
    ctx = types.SimpleNamespace(services=services, project=project)
    return types.SimpleNamespace(ctx=ctx)


async def test_recall_returns_scope_filtered_bundle(store):
    await _add(store, "timur prefers tea over coffee", USER, "u1")
    await _add(store, "project deadline is friday", PROJECT, "p1")

    retriever = Retriever(
        store,
        FakeEmbedder(_vocab("timur prefers tea over coffee project deadline friday")),
        None,  # no model wired -> verbatim render, never an LLM call
        model="",
    )
    execution = _execution(services={MEMORY_READ_SERVICE: retriever})

    result = await recall(execution, RecallInput(query="what does timur drink"))

    assert not result.is_error
    assert "tea" in result.content
    assert "friday" not in result.content  # PROJECT scope excluded when USER-only
    assert "Recalled 1 item" in result.preview


async def test_recall_project_scope_unions_user(store):
    await _add(store, "timur prefers tea over coffee", USER, "u1")
    await _add(store, "project ships on friday", PROJECT, "p1")

    retriever = Retriever(
        store,
        FakeEmbedder(_vocab("timur prefers tea over coffee project ships friday")),
        None,
        model="",
    )
    project = types.SimpleNamespace(project_id="proj-1")
    execution = _execution(services={MEMORY_READ_SERVICE: retriever}, project=project)

    result = await recall(execution, RecallInput(query="friday ship and tea"))

    assert not result.is_error
    # PROJECT primary + USER also-scope: both lenses are recallable.
    assert "friday" in result.content
    assert "tea" in result.content


async def test_recall_empty_pool_is_not_an_error(store):
    retriever = Retriever(store, FakeEmbedder(_vocab("anything")), None, model="")
    execution = _execution(services={MEMORY_READ_SERVICE: retriever})

    result = await recall(execution, RecallInput(query="nothing stored yet"))

    assert not result.is_error
    assert result.content == "No relevant memory found."
    assert result.preview == "Nothing recalled"


async def test_recall_unavailable_service_errors(store):
    execution = _execution(services={})  # memory_read not wired
    result = await recall(execution, RecallInput(query="anything"))

    assert result.is_error
    assert "not available" in result.content
