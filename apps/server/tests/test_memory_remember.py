"""remember()/recall()/forget() tools over the FLAT RecordStore (ntrp/tools/memory.py).

The tools add/search/delete atomic records via a real tmp RecordStore
(`search_index=None` -> FTS-only, no embeddings, no search.db). No scope, no lens
tool. A minimal namespace stands in for ToolExecution (the executors read only
ctx.services / ctx.session_id and execution.tool_id).
"""

import types
from pathlib import Path

import pytest

from ntrp.memory.records import RecordStore
from ntrp.tools.memory import (
    MEMORY_RECORDS_SERVICE,
    ForgetInput,
    RecallInput,
    RememberInput,
    forget,
    recall,
    remember,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def store(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path / "memory.db", search_index=None)


def _execution(store):
    ctx = types.SimpleNamespace(
        services={MEMORY_RECORDS_SERVICE: store},
        session_id="s1",
    )
    return types.SimpleNamespace(ctx=ctx, tool_id="t1")


# --- remember -----------------------------------------------------------------


async def test_remember_adds_a_record_with_kind(store: RecordStore):
    execution = _execution(store)
    result = await remember(
        execution, RememberInput(text="the user prefers tea", kind="preference")
    )

    assert not result.is_error
    assert result.preview == "Remembered"

    hits = await store.search("tea")
    assert len(hits) == 1
    assert hits[0].text == "the user prefers tea"
    assert hits[0].kind == "preference"
    # Provenance footnote retained from the chat turn.
    assert hits[0].source_ref is not None
    assert hits[0].source_ref.kind == "chat_turn"


async def test_remember_defaults_kind_to_note(store: RecordStore):
    execution = _execution(store)
    await remember(execution, RememberInput(text="a loose observation"))
    hits = await store.search("observation")
    assert hits[0].kind == "note"


# --- recall -------------------------------------------------------------------


async def test_recall_returns_hybrid_hits(store: RecordStore):
    execution = _execution(store)
    await store.add("the user lives in Berlin")
    await store.add("the user enjoys hiking")

    result = await recall(execution, RecallInput(query="Berlin"))
    assert not result.is_error
    assert "Berlin" in result.content


async def test_recall_no_matches(store: RecordStore):
    execution = _execution(store)
    await store.add("the user likes tea")
    result = await recall(execution, RecallInput(query="quantum chromodynamics"))
    assert result.preview == "No matches"


# --- forget -------------------------------------------------------------------


async def test_forget_deletes_best_match(store: RecordStore):
    execution = _execution(store)
    await store.add("the user dislikes coffee")

    result = await forget(execution, ForgetInput(query="coffee"))
    assert result.preview == "Forgotten"
    assert "coffee" in result.content.lower()
    assert await store.search("coffee") == []


async def test_forget_lists_other_matches(store: RecordStore):
    execution = _execution(store)
    await store.add("the user likes green tea")
    await store.add("the user likes black tea")

    result = await forget(execution, ForgetInput(query="tea"))
    assert result.preview == "Forgotten"
    assert "Other matches" in result.content
    remaining = await store.search("tea")
    assert len(remaining) == 1


async def test_forget_not_found(store: RecordStore):
    execution = _execution(store)
    result = await forget(execution, ForgetInput(query="nothing stored"))
    assert result.preview == "Not found"


# --- unavailable service (shape preserved) ------------------------------------


async def test_remember_unavailable_service_errors():
    ctx = types.SimpleNamespace(services={}, session_id="s1")
    execution = types.SimpleNamespace(ctx=ctx, tool_id="t1")

    result = await remember(execution, RememberInput(text="anything"))
    assert result.is_error
    assert "not available" in result.content
