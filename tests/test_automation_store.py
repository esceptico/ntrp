from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.automation.store import AutomationStore


@pytest_asyncio.fixture
async def automation_store(tmp_path: Path):
    conn = await database.connect(tmp_path / "automation.db")
    store = AutomationStore(conn)
    await store.init_schema()
    yield store
    await conn.close()


@pytest.mark.asyncio
async def test_count_state_is_persistent_and_clearable(automation_store: AutomationStore):
    now = datetime.now(UTC)

    assert await automation_store.increment_count("task-1", "session-1", now) == 1
    assert await automation_store.increment_count("task-1", "session-1", now) == 2
    assert await automation_store.increment_count("task-1", "session-2", now) == 1

    await automation_store.clear_count("task-1", "session-1")

    assert await automation_store.increment_count("task-1", "session-1", now) == 1
    assert await automation_store.increment_count("task-1", "session-2", now) == 2


@pytest.mark.asyncio
async def test_chat_extraction_state_tracks_pending_and_cursor(automation_store: AutomationStore):
    now = datetime.now(UTC)
    messages = (
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
    )

    await automation_store.record_chat_extraction_activity("session-1", messages, now)

    assert await automation_store.get_chat_extraction_cursor("session-1") == 0
    assert await automation_store.list_pending_chat_extractions() == [("session-1", 0, messages)]

    await automation_store.mark_chat_extraction_extracted("session-1", 2, now)
    assert await automation_store.list_pending_chat_extractions() == []

    next_messages = messages + ({"role": "user", "content": "three"},)
    await automation_store.record_chat_extraction_activity("session-1", next_messages, now)

    assert await automation_store.get_chat_extraction_cursor("session-1") == 2
    assert await automation_store.list_pending_chat_extractions() == [("session-1", 2, next_messages)]
