from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.automation.builtins import seed_builtins
from ntrp.automation.models import Automation
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import KnowledgeEventTrigger, TimeTrigger
from ntrp.constants import (
    BUILTIN_KNOWLEDGE_HEALTH_ID,
    BUILTIN_KNOWLEDGE_PROFILE_REFRESH_ID,
    BUILTIN_KNOWLEDGE_REFLECTION_ID,
    BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID,
    BUILTIN_KNOWLEDGE_RETENTION_ID,
    BUILTIN_PATTERN_FINDER_DAILY_ID,
)
from ntrp.knowledge import KnowledgeObjectType


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
    name: str | None = None,
    enabled: bool = True,
    next_run_at: datetime | None = None,
    running_since: datetime | None = None,
    handler: str | None = None,
    builtin: bool = False,
) -> Automation:
    return Automation(
        task_id=task_id,
        name=name or task_id,
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
        handler=handler,
        builtin=builtin,
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
    await automation_store.enqueue_event("event-task", "event-dead", "{}", now - timedelta(minutes=1))
    dead_claim = await automation_store.claim_next_event("event-task", now)
    await automation_store.dead_letter_event(dead_claim[0], "gave up", now)

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
    assert status["dead_letters"]["total"] == 1
    assert status["dead_letters"]["newest_failed_at"] is not None


@pytest.mark.asyncio
async def test_event_dead_letter_preserves_failed_payload_and_removes_from_queue(automation_store: AutomationStore):
    now = datetime.now(UTC)
    await automation_store.enqueue_event("event-task", "event-dead", '{"ok": true}', now)
    claimed = await automation_store.claim_next_event("event-task", now)

    await automation_store.dead_letter_event(claimed[0], "too many failures", now + timedelta(seconds=1))

    assert await automation_store.claim_next_event("event-task", now + timedelta(seconds=2)) is None
    rows = await automation_store.conn.execute_fetchall("SELECT * FROM automation_event_dead_letter")
    assert len(rows) == 1
    assert rows[0]["task_id"] == "event-task"
    assert rows[0]["event_key"] == "event-dead"
    assert rows[0]["context"] == '{"ok": true}'
    assert rows[0]["last_error"] == "too many failures"
    assert rows[0]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_dead_letter_event_rolls_back_copy_when_queue_delete_fails(automation_store: AutomationStore):
    now = datetime.now(UTC)
    await automation_store.enqueue_event("event-task", "event-dead", '{"ok": true}', now)
    claimed = await automation_store.claim_next_event("event-task", now)
    await automation_store.conn.execute(
        """
        CREATE TRIGGER fail_event_queue_delete
        BEFORE DELETE ON automation_event_queue
        BEGIN
            SELECT RAISE(ABORT, 'queue delete failed');
        END
        """
    )
    await automation_store.conn.commit()

    with pytest.raises(Exception, match="queue delete failed"):
        await automation_store.dead_letter_event(claimed[0], "too many failures", now)
    await automation_store.conn.commit()

    dead_rows = await automation_store.conn.execute_fetchall("SELECT * FROM automation_event_dead_letter")
    queue_rows = await automation_store.conn.execute_fetchall("SELECT * FROM automation_event_queue")

    assert dead_rows == []
    assert len(queue_rows) == 1


@pytest.mark.asyncio
async def test_claim_and_enqueue_event_dedupes_in_one_store_call(automation_store: AutomationStore):
    now = datetime.now(UTC)

    assert await automation_store.claim_and_enqueue_event("event-task", "event-1", '{"ok": true}', now) is True
    assert await automation_store.claim_and_enqueue_event("event-task", "event-1", '{"ok": false}', now) is False

    queue_rows = await automation_store.conn.execute_fetchall(
        "SELECT task_id, event_key, context FROM automation_event_queue"
    )
    dedupe_rows = await automation_store.conn.execute_fetchall("SELECT task_id, event_key FROM automation_event_dedupe")

    assert [dict(row) for row in queue_rows] == [
        {"task_id": "event-task", "event_key": "event-1", "context": '{"ok": true}'}
    ]
    assert [dict(row) for row in dedupe_rows] == [{"task_id": "event-task", "event_key": "event-1"}]


@pytest.mark.asyncio
async def test_claim_and_enqueue_event_rolls_back_dedupe_when_enqueue_fails(automation_store: AutomationStore):
    now = datetime.now(UTC)
    await automation_store.conn.execute(
        """
        CREATE TRIGGER fail_event_queue_insert
        BEFORE INSERT ON automation_event_queue
        BEGIN
            SELECT RAISE(ABORT, 'queue insert failed');
        END
        """
    )
    await automation_store.conn.commit()

    with pytest.raises(Exception, match="queue insert failed"):
        await automation_store.claim_and_enqueue_event("event-task", "event-1", "{}", now)

    rows = await automation_store.conn.execute_fetchall(
        "SELECT * FROM automation_event_dedupe WHERE task_id = ?",
        ("event-task",),
    )

    assert rows == []


@pytest.mark.asyncio
async def test_seed_builtins_uses_knowledge_handlers(automation_store: AutomationStore):
    await seed_builtins(automation_store)

    automations = {automation.task_id: automation for automation in await automation_store.list_all()}

    assert {
        BUILTIN_KNOWLEDGE_REFLECTION_ID,
        BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID,
        BUILTIN_KNOWLEDGE_PROFILE_REFRESH_ID,
        BUILTIN_KNOWLEDGE_RETENTION_ID,
        BUILTIN_KNOWLEDGE_HEALTH_ID,
        BUILTIN_PATTERN_FINDER_DAILY_ID,
    } <= set(automations)
    assert automations[BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID].handler == "knowledge_reflection"
    assert automations[BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID].enabled is True
    profile_refresh = automations[BUILTIN_KNOWLEDGE_PROFILE_REFRESH_ID]
    assert profile_refresh.handler == "knowledge_profile_refresh"
    assert profile_refresh.enabled is False
    assert profile_refresh.triggers == []
    assert profile_refresh.writable is True
    assert any(
        isinstance(trigger, KnowledgeEventTrigger)
        and trigger.object_types == (KnowledgeObjectType.MEMORY_EPISODE.value,)
        and trigger.actions == ("created",)
        for trigger in automations[BUILTIN_KNOWLEDGE_REFLECTION_ID].triggers
    )
    assert automations[BUILTIN_KNOWLEDGE_RETENTION_ID].handler == "knowledge_retention"
    assert automations[BUILTIN_KNOWLEDGE_RETENTION_ID].enabled is True
    assert automations[BUILTIN_KNOWLEDGE_RETENTION_ID].writable is False
    assert "stale generated knowledge objects" in automations[BUILTIN_KNOWLEDGE_RETENTION_ID].description
    assert automations[BUILTIN_KNOWLEDGE_HEALTH_ID].handler == "knowledge_health"
    assert automations[BUILTIN_KNOWLEDGE_HEALTH_ID].enabled is True
    assert automations[BUILTIN_KNOWLEDGE_HEALTH_ID].writable is False
    assert automations[BUILTIN_PATTERN_FINDER_DAILY_ID].handler == "pattern_finder_daily"
    assert automations[BUILTIN_PATTERN_FINDER_DAILY_ID].enabled is True
    assert any(isinstance(trigger, TimeTrigger) for trigger in automations[BUILTIN_PATTERN_FINDER_DAILY_ID].triggers)
    assert all(automation.handler != "learning_review" for automation in automations.values())


@pytest.mark.asyncio
async def test_seed_builtins_removes_stale_knowledge_builtins(automation_store: AutomationStore):
    stale_builtins = [
        ("builtin:chat-extraction", "Knowledge Reflection", "knowledge_reflection"),
        ("builtin:consolidation", "Knowledge Consolidation", "knowledge_reflection"),
        ("builtin:memory-maintenance", "Knowledge Retention", "knowledge_retention"),
        ("builtin:memory-health", "Knowledge Health Audit", "knowledge_health"),
    ]
    for task_id, name, handler in stale_builtins:
        await automation_store.save(_automation(task_id, name=name, handler=handler, builtin=True))
    await automation_store.save(_automation("builtin:other", name="Other Builtin", handler="other", builtin=True))
    await automation_store.save(_automation("user-knowledge", handler="knowledge_reflection", builtin=False))

    await seed_builtins(automation_store)

    automations = {automation.task_id: automation for automation in await automation_store.list_all()}
    assert {task_id for task_id, _, _ in stale_builtins}.isdisjoint(automations)
    assert "builtin:other" in automations
    assert "user-knowledge" in automations
    assert {
        BUILTIN_KNOWLEDGE_REFLECTION_ID,
        BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID,
        BUILTIN_KNOWLEDGE_PROFILE_REFRESH_ID,
        BUILTIN_KNOWLEDGE_RETENTION_ID,
        BUILTIN_KNOWLEDGE_HEALTH_ID,
        BUILTIN_PATTERN_FINDER_DAILY_ID,
    } <= set(automations)


@pytest.mark.asyncio
async def test_loop_fields_roundtrip(automation_store: AutomationStore):
    now = datetime.now(UTC)
    loop = Automation(
        task_id="loop-foo",
        name="Loop: check CI",
        description="check CI",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=now,
        next_run_at=now + timedelta(minutes=5),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess-1",
        loop_prompt="check CI",
        max_iterations=3,
        iteration_count=0,
        stop_when="when green",
    )
    await automation_store.save(loop)

    loaded = await automation_store.get("loop-foo")
    assert loaded is not None
    assert loaded.kind == "loop"
    assert loaded.target_session_id == "sess-1"
    assert loaded.loop_prompt == "check CI"
    assert loaded.max_iterations == 3
    assert loaded.iteration_count == 0
    assert loaded.stop_when == "when green"


@pytest.mark.asyncio
async def test_list_loops_by_session_filters_correctly(automation_store: AutomationStore):
    now = datetime.now(UTC)

    def _loop(task_id: str, session_id: str) -> Automation:
        return Automation(
            task_id=task_id,
            name=task_id,
            description="x",
            model=None,
            triggers=[TimeTrigger(every="5m")],
            enabled=True,
            created_at=now,
            next_run_at=now,
            last_run_at=None,
            last_result=None,
            running_since=None,
            writable=True,
            kind="loop",
            target_session_id=session_id,
            loop_prompt="x",
        )

    await automation_store.save(_loop("loop-a", "sess-1"))
    await automation_store.save(_loop("loop-b", "sess-1"))
    await automation_store.save(_loop("loop-c", "sess-2"))
    # Non-loop in same session should not appear.
    await automation_store.save(_automation("not-a-loop"))

    by_one = await automation_store.list_loops_by_session("sess-1")
    assert sorted(a.task_id for a in by_one) == ["loop-a", "loop-b"]

    by_two = await automation_store.list_loops_by_session("sess-2")
    assert [a.task_id for a in by_two] == ["loop-c"]


@pytest.mark.asyncio
async def test_increment_iteration_advances_count(automation_store: AutomationStore):
    now = datetime.now(UTC)
    loop = Automation(
        task_id="loop-iter",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=now,
        next_run_at=now,
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess",
        loop_prompt="x",
    )
    await automation_store.save(loop)

    await automation_store.increment_iteration("loop-iter")
    await automation_store.increment_iteration("loop-iter")

    loaded = await automation_store.get("loop-iter")
    assert loaded is not None
    assert loaded.iteration_count == 2


@pytest.mark.asyncio
async def test_v5_fields_roundtrip(automation_store: AutomationStore):
    """All new v5 fields must serialize/deserialize through save/get."""
    now = datetime.now(UTC)
    automation = Automation(
        task_id="post-mode-foo",
        name="Post offer update",
        description="Posts to a channel",
        model=None,
        triggers=[TimeTrigger(every="4h")],
        enabled=True,
        created_at=now,
        next_run_at=now + timedelta(hours=4),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        thread_id="channel-sess-1",
        read_history=False,
        parent_automation_id="watcher-1",
        idempotency_key="offer-42",
        idempotency_scope="global",
    )
    await automation_store.save(automation)

    loaded = await automation_store.get("post-mode-foo")
    assert loaded is not None
    assert loaded.thread_id == "channel-sess-1"
    assert loaded.read_history is False
    assert loaded.parent_automation_id == "watcher-1"
    assert loaded.idempotency_key == "offer-42"
    assert loaded.idempotency_scope == "global"


@pytest.mark.asyncio
async def test_v5_fields_default_to_none_or_false(automation_store: AutomationStore):
    """Existing call sites that don't set v5 fields still roundtrip cleanly."""
    automation = _automation("plain")
    await automation_store.save(automation)

    loaded = await automation_store.get("plain")
    assert loaded is not None
    assert loaded.thread_id is None
    assert loaded.read_history is False
    assert loaded.parent_automation_id is None
    assert loaded.idempotency_key is None
    assert loaded.idempotency_scope is None


@pytest.mark.asyncio
async def test_update_metadata_persists_v5_identity_fields(automation_store: AutomationStore):
    """update_metadata() must persist parent_automation_id / idempotency_key / idempotency_scope."""
    automation = _automation("identity-fields")
    await automation_store.save(automation)

    automation.parent_automation_id = "watcher-7"
    automation.idempotency_key = "offer-99"
    automation.idempotency_scope = "thread"
    await automation_store.update_metadata(automation)

    loaded = await automation_store.get("identity-fields")
    assert loaded is not None
    assert loaded.parent_automation_id == "watcher-7"
    assert loaded.idempotency_key == "offer-99"
    assert loaded.idempotency_scope == "thread"


@pytest.mark.asyncio
async def test_v5_migration_backfills_loop_rows(tmp_path: Path):
    """v4 → v5: loop rows get thread_id = target_session_id, read_history = True."""
    db_path = tmp_path / "v4.db"
    conn = await database.connect(db_path)

    # Manually build a v4 schema: scheduled_tasks with loop columns, no v5 columns.
    await conn.executescript(
        """
        CREATE TABLE automation_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE scheduled_tasks (
            task_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL,
            model TEXT,
            triggers TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_run_at TEXT,
            next_run_at TEXT,
            notifiers TEXT,
            last_result TEXT,
            running_since TEXT,
            writable INTEGER NOT NULL DEFAULT 0,
            handler TEXT,
            builtin INTEGER NOT NULL DEFAULT 0,
            cooldown_minutes INTEGER,
            kind TEXT NOT NULL DEFAULT 'automation',
            target_session_id TEXT,
            loop_prompt TEXT,
            max_iterations INTEGER,
            iteration_count INTEGER NOT NULL DEFAULT 0,
            stop_when TEXT,
            max_age_days INTEGER
        );
        INSERT INTO automation_meta (key, value) VALUES ('schema_version', '4');
        """
    )
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        """
        INSERT INTO scheduled_tasks (
            task_id, name, description, model, triggers, enabled, created_at,
            kind, target_session_id, loop_prompt
        ) VALUES (?, '', 'loop a', NULL, '[]', 1, ?, 'loop', 'sess-A', 'prompt a')
        """,
        ("loop-row", now),
    )
    await conn.execute(
        """
        INSERT INTO scheduled_tasks (
            task_id, name, description, model, triggers, enabled, created_at,
            kind, target_session_id, loop_prompt
        ) VALUES (?, '', 'plain', NULL, '[]', 1, ?, 'automation', NULL, NULL)
        """,
        ("plain-row", now),
    )
    await conn.commit()

    # Run migration via init_schema.
    store = AutomationStore(conn)
    await store.init_schema()

    loaded_loop = await store.get("loop-row")
    assert loaded_loop is not None
    assert loaded_loop.thread_id == "sess-A"
    assert loaded_loop.read_history is True

    loaded_plain = await store.get("plain-row")
    assert loaded_plain is not None
    assert loaded_plain.thread_id is None
    assert loaded_plain.read_history is False

    await conn.close()


@pytest.mark.asyncio
async def test_v5_migration_is_idempotent(tmp_path: Path):
    """Running migration twice doesn't double-write or fail."""
    db_path = tmp_path / "v4.db"
    conn = await database.connect(db_path)
    await conn.executescript(
        """
        CREATE TABLE automation_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE scheduled_tasks (
            task_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL,
            model TEXT,
            triggers TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_run_at TEXT,
            next_run_at TEXT,
            notifiers TEXT,
            last_result TEXT,
            running_since TEXT,
            writable INTEGER NOT NULL DEFAULT 0,
            handler TEXT,
            builtin INTEGER NOT NULL DEFAULT 0,
            cooldown_minutes INTEGER,
            kind TEXT NOT NULL DEFAULT 'automation',
            target_session_id TEXT,
            loop_prompt TEXT,
            max_iterations INTEGER,
            iteration_count INTEGER NOT NULL DEFAULT 0,
            stop_when TEXT,
            max_age_days INTEGER
        );
        INSERT INTO automation_meta (key, value) VALUES ('schema_version', '4');
        """
    )
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        """
        INSERT INTO scheduled_tasks (
            task_id, name, description, model, triggers, enabled, created_at,
            kind, target_session_id, loop_prompt
        ) VALUES (?, '', 'loop a', NULL, '[]', 1, ?, 'loop', 'sess-A', 'prompt a')
        """,
        ("loop-row", now),
    )
    await conn.commit()

    store = AutomationStore(conn)
    await store.init_schema()
    # After v5, this row has thread_id='sess-A', read_history=True.
    # Now hand-modify thread_id to simulate a write that should NOT be clobbered
    # by a second migration pass.
    await conn.execute(
        "UPDATE scheduled_tasks SET thread_id = ? WHERE task_id = ?",
        ("user-edited-thread", "loop-row"),
    )
    await conn.commit()

    # Re-run init_schema; should be a no-op for the backfill since version is now 5.
    await store.init_schema()
    loaded = await store.get("loop-row")
    assert loaded is not None
    assert loaded.thread_id == "user-edited-thread"

    await conn.close()


@pytest.mark.asyncio
async def test_v5_indexes_created(automation_store: AutomationStore):
    """The three new v5 indexes must exist after init_schema."""
    rows = await automation_store.conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type = 'index'")
    names = {row["name"] for row in rows}
    assert "idx_scheduled_tasks_parent" in names
    assert "idx_scheduled_tasks_thread_kind" in names
    assert "idx_scheduled_tasks_idempotency" in names


def test_scheduler_constructor_has_no_learning_recorder(automation_store: AutomationStore):
    async def record_learning_event(**event):
        raise AssertionError("scheduler should not write continual-learning events")

    with pytest.raises(TypeError):
        Scheduler(
            store=automation_store,
            build_deps=lambda: None,
            record_learning_event=record_learning_event,
        )
