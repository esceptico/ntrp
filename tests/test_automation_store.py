from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.automation.builtins import seed_builtins
from ntrp.automation.models import Automation
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import TimeTrigger
from ntrp.constants import (
    BUILTIN_CHAT_EXTRACTION_ID,
    BUILTIN_CONSOLIDATION_ID,
    BUILTIN_LEARNING_REVIEW_ID,
    BUILTIN_MEMORY_HEALTH_ID,
    BUILTIN_MEMORY_MAINTENANCE_ID,
)


@pytest_asyncio.fixture
async def automation_store(tmp_path: Path):
    conn = await database.connect(tmp_path / "automation.db")
    store = AutomationStore(conn)
    await store.init_schema()
    yield store
    await conn.close()


def _automation(
    task_id: str,
    *,
    enabled: bool = True,
    next_run_at: datetime | None = None,
    running_since: datetime | None = None,
) -> Automation:
    return Automation(
        task_id=task_id,
        name=task_id,
        description=f"{task_id} description",
        model=None,
        triggers=[TimeTrigger(at="09:00")],
        enabled=enabled,
        created_at=datetime.now(UTC),
        next_run_at=next_run_at,
        last_run_at=None,
        last_result=None,
        running_since=running_since,
        writable=False,
    )


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


@pytest.mark.asyncio
async def test_status_summarizes_scheduler_owned_state(automation_store: AutomationStore):
    now = datetime.now(UTC)
    await automation_store.save(_automation("due", next_run_at=now - timedelta(minutes=5)))
    await automation_store.save(_automation("future", next_run_at=now + timedelta(hours=1)))
    await automation_store.save(_automation("disabled", enabled=False, next_run_at=now - timedelta(minutes=5)))
    await automation_store.save(
        _automation("running", next_run_at=now - timedelta(minutes=5), running_since=now - timedelta(minutes=10))
    )

    await automation_store.enqueue_event("event-task", "event-1", "{}", now - timedelta(minutes=3))
    await automation_store.enqueue_event("event-task", "event-2", "{}", now - timedelta(minutes=2))
    claimed = await automation_store.claim_next_event("event-task", now)
    await automation_store.fail_event(claimed[0], "try later", now + timedelta(minutes=30))
    await automation_store.claim_next_event("event-task", now)

    await automation_store.increment_count("count-task", "session-1", now - timedelta(minutes=20))
    await automation_store.record_chat_extraction_activity(
        "session-1",
        ({"role": "user", "content": "hello"},),
        now - timedelta(minutes=15),
    )

    status = await automation_store.get_status(now)

    assert status["tasks"]["total"] == 4
    assert status["tasks"]["enabled"] == 3
    assert status["tasks"]["disabled"] == 1
    assert status["tasks"]["running"] == 1
    assert status["tasks"]["due"] == 1
    assert status["tasks"]["next_run_at"] is not None
    assert status["tasks"]["oldest_running_since"] is not None
    assert status["event_queue"]["total"] == 2
    assert status["event_queue"]["ready"] == 0
    assert status["event_queue"]["scheduled"] == 1
    assert status["event_queue"]["claimed"] == 1
    assert status["count_state"]["total"] == 1
    assert status["chat_extraction"]["total"] == 1
    assert status["chat_extraction"]["pending"] == 1


@pytest.mark.asyncio
async def test_seed_builtins_splits_memory_jobs(automation_store: AutomationStore):
    await seed_builtins(automation_store)

    automations = {automation.task_id: automation for automation in await automation_store.list_all()}

    assert {
        BUILTIN_CHAT_EXTRACTION_ID,
        BUILTIN_CONSOLIDATION_ID,
        BUILTIN_MEMORY_MAINTENANCE_ID,
        BUILTIN_MEMORY_HEALTH_ID,
        BUILTIN_LEARNING_REVIEW_ID,
    } <= set(automations)
    assert automations[BUILTIN_CONSOLIDATION_ID].handler == "consolidation"
    assert automations[BUILTIN_MEMORY_MAINTENANCE_ID].handler == "memory_maintenance"
    assert automations[BUILTIN_MEMORY_MAINTENANCE_ID].writable is True
    assert automations[BUILTIN_MEMORY_HEALTH_ID].handler == "memory_health"
    assert automations[BUILTIN_MEMORY_HEALTH_ID].writable is False
    assert automations[BUILTIN_LEARNING_REVIEW_ID].handler == "learning_review"
    assert automations[BUILTIN_LEARNING_REVIEW_ID].writable is True
