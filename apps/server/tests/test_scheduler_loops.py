import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.agent import Usage
from ntrp.automation.models import Automation
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import TimeTrigger


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "automation.db")
    s = AutomationStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


def _loop(
    task_id: str = "loop-1",
    *,
    session_id: str = "sess-1",
    prompt: str = "check CI",
    every: str = "5m",
    max_iterations: int | None = None,
    iteration_count: int = 0,
    next_run_at: datetime | None = None,
    read_history: bool = True,
    thread_id: str | None = None,
) -> Automation:
    now = datetime.now(UTC)
    return Automation(
        task_id=task_id,
        name=f"Loop: {prompt[:40]}",
        description=prompt,
        model=None,
        triggers=[TimeTrigger(every=every)],
        enabled=True,
        created_at=now,
        next_run_at=next_run_at or (now - timedelta(seconds=1)),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id=session_id,
        loop_prompt=prompt,
        max_iterations=max_iterations,
        iteration_count=iteration_count,
        read_history=read_history,
        thread_id=thread_id if thread_id is not None else session_id,
    )


def _make_scheduler(store: AutomationStore) -> tuple[Scheduler, list[Automation]]:
    dispatched: list[Automation] = []

    async def dispatcher(auto: Automation) -> str | None:
        dispatched.append(auto)
        return "fake-run-id"

    sched = Scheduler(store=store, build_deps=lambda: None)
    sched.set_iteration_dispatcher(dispatcher)
    return sched, dispatched


def _make_post_scheduler(
    store: AutomationStore,
) -> tuple[Scheduler, list[Automation], list[str]]:
    """Scheduler wired with only a post dispatcher (returns the agent's text result)."""
    dispatched: list[Automation] = []
    results: list[str] = []

    async def post_dispatcher(auto: Automation) -> str | None:
        dispatched.append(auto)
        result = f"agent result for {auto.task_id}"
        results.append(result)
        return result

    sched = Scheduler(store=store, build_deps=lambda: None)
    sched.set_post_dispatcher(post_dispatcher)
    return sched, dispatched, results


@pytest.mark.asyncio
async def test_scheduler_dispatches_due_loop(store: AutomationStore):
    await store.save(_loop())
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    # Loops fire asynchronously through _start_run → _run_and_finalize.
    # Drain the scheduler's tracked tasks.
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    assert dispatched[0].task_id == "loop-1"
    assert dispatched[0].loop_prompt == "check CI"

    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 1
    assert reloaded.enabled is True
    assert reloaded.next_run_at is not None and reloaded.next_run_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_scheduler_wakes_at_rescheduled_loop_time(store: AutomationStore):
    await store.save(_loop(every="1m"))
    sched, _ = _make_scheduler(store)

    await sched._tick()

    reloaded = await store.get("loop-1")
    assert reloaded.next_run_at is not None
    assert sched._wake_deadline == reloaded.next_run_at
    assert sched._wake_task is not None

    sched._wake_task.cancel()
    try:
        await sched._wake_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_max_iterations_disables_loop(store: AutomationStore):
    await store.save(_loop(max_iterations=2, iteration_count=1))
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 2
    assert reloaded.enabled is False


@pytest.mark.asyncio
async def test_loop_without_dispatcher_raises(store: AutomationStore):
    await store.save(_loop())
    sched = Scheduler(store=store, build_deps=lambda: None)  # no dispatcher

    await sched._tick()
    for t in list(sched._running):
        await t

    # Loop run failed (no dispatcher); iteration_count untouched, next_run advanced.
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 0


@pytest.mark.asyncio
async def test_create_loop_via_service_stores_correctly(store: AutomationStore):
    sched, _ = _make_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)

    loop = await svc.create_loop(
        session_id="sess-1",
        prompt="watch CI",
        every="5m",
        max_iterations=10,
        stop_when="when green",
    )

    assert loop.kind == "loop"
    assert loop.target_session_id == "sess-1"
    assert loop.loop_prompt == "watch CI"
    assert loop.max_iterations == 10
    assert loop.stop_when == "when green"
    assert loop.triggers[0].params()["every"] == "5m"

    loops = await svc.list_loops_by_session("sess-1")
    assert [a.task_id for a in loops] == [loop.task_id]


@pytest.mark.asyncio
async def test_create_loop_rejects_empty_prompt(store: AutomationStore):
    sched, _ = _make_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)

    with pytest.raises(ValueError, match="prompt"):
        await svc.create_loop(session_id="s", prompt="   ", every="5m")


@pytest.mark.asyncio
async def test_create_loop_sets_next_run_at_to_now(store: AutomationStore):
    # First fire happens "as soon as session is idle" — next_run_at = now
    # so the scheduler picks it up immediately (or the run-completed
    # fast-path fires it the moment the /loop turn ends).
    sched, _ = _make_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)
    before = datetime.now(UTC)

    loop = await svc.create_loop(session_id="sess-1", prompt="watch CI", every="5m")

    assert loop.next_run_at is not None
    # within a second of creation
    assert abs((loop.next_run_at - before).total_seconds()) < 1


@pytest.mark.asyncio
async def test_loop_fire_gate_defers_while_session_busy(store: AutomationStore):
    # Loop is due; the fire gate says "no, session has an active run" →
    # scheduler skips it. iteration_count stays at 0; next_run_at stays
    # in the past so the next tick re-evaluates.
    await store.save(_loop())
    sched, dispatched = _make_scheduler(store)
    sched.set_loop_fire_gate(lambda _auto: False)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert dispatched == []
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 0
    assert reloaded.next_run_at is not None
    assert reloaded.next_run_at <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_loop_fire_gate_allows_when_session_idle(store: AutomationStore):
    await store.save(_loop())
    sched, dispatched = _make_scheduler(store)
    sched.set_loop_fire_gate(lambda _auto: True)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 1


@pytest.mark.asyncio
async def test_handle_run_completed_fires_due_loops_for_session(store: AutomationStore):
    from ntrp.events.internal import RunCompleted

    await store.save(_loop(session_id="sess-1"))
    sched, dispatched = _make_scheduler(store)

    await sched.handle_run_completed(
        RunCompleted(run_id="run-x", session_id="sess-1", messages=(), usage=Usage(), result=None)
    )
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    assert dispatched[0].target_session_id == "sess-1"


@pytest.mark.asyncio
async def test_handle_run_completed_ignores_other_sessions(store: AutomationStore):
    from ntrp.events.internal import RunCompleted

    await store.save(_loop(session_id="sess-1"))
    sched, dispatched = _make_scheduler(store)

    await sched.handle_run_completed(
        RunCompleted(run_id="run-x", session_id="sess-other", messages=(), usage=Usage(), result=None)
    )
    for t in list(sched._running):
        await t

    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_run_completed_skips_loop_not_yet_due(store: AutomationStore):
    from ntrp.events.internal import RunCompleted

    future_loop = _loop(next_run_at=datetime.now(UTC) + timedelta(minutes=5))
    await store.save(future_loop)
    sched, dispatched = _make_scheduler(store)

    await sched.handle_run_completed(
        RunCompleted(run_id="run-x", session_id="sess-1", messages=(), usage=Usage(), result=None)
    )
    for t in list(sched._running):
        await t

    assert dispatched == []


@pytest.mark.asyncio
async def test_max_iterations_loop_clears_next_run_at(store: AutomationStore):
    # Fire the final iteration of a 2-iter loop. After it, the loop should
    # be disabled AND next_run_at should be None (no future countdown for
    # a loop that will never fire again).
    await store.save(_loop(max_iterations=2, iteration_count=1))
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    reloaded = await store.get("loop-1")
    assert reloaded.enabled is False
    assert reloaded.next_run_at is None


@pytest.mark.asyncio
async def test_aged_out_loop_clears_next_run_at(store: AutomationStore):
    old = datetime.now(UTC) - timedelta(days=8)
    loop = Automation(
        task_id="loop-old",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=old,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess",
        loop_prompt="check x",
        max_age_days=7,
    )
    await store.save(loop)
    sched, _ = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    reloaded = await store.get("loop-old")
    assert reloaded.enabled is False
    assert reloaded.next_run_at is None


@pytest.mark.asyncio
async def test_aged_out_loop_disables_without_firing(store: AutomationStore):
    # Loop created 8 days ago, max_age_days=7 → aged out.
    old = datetime.now(UTC) - timedelta(days=8)
    loop = Automation(
        task_id="loop-old",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=old,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess",
        loop_prompt="check x",
        max_age_days=7,
    )
    await store.save(loop)
    sched, dispatched = _make_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert dispatched == []  # never dispatched
    reloaded = await store.get("loop-old")
    assert reloaded.enabled is False
    assert reloaded.iteration_count == 0


# ---------------------------------------------------------------------------
# Post mode (channel monitor): read_history=False, agent runs fresh, result
# is appended into the target session as an assistant message.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_mode_dispatches_when_due(store: AutomationStore):
    await store.save(_loop(session_id="sess-post", read_history=False, thread_id="sess-post"))
    sched, dispatched, _results = _make_post_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    assert dispatched[0].task_id == "loop-1"
    assert dispatched[0].read_history is False

    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 1
    assert reloaded.enabled is True


@pytest.mark.asyncio
async def test_post_mode_routes_to_post_not_iteration_dispatcher(store: AutomationStore):
    """A post-mode loop must NOT call the iteration dispatcher."""
    await store.save(_loop(read_history=False))
    iteration_calls: list[Automation] = []
    post_calls: list[Automation] = []

    async def iteration(auto: Automation) -> str | None:
        iteration_calls.append(auto)
        return "iter-id"

    async def post(auto: Automation) -> str | None:
        post_calls.append(auto)
        return "posted text"

    sched = Scheduler(store=store, build_deps=lambda: None)
    sched.set_iteration_dispatcher(iteration)
    sched.set_post_dispatcher(post)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert iteration_calls == []
    assert len(post_calls) == 1


@pytest.mark.asyncio
async def test_iteration_mode_routes_to_iteration_not_post_dispatcher(store: AutomationStore):
    """An iteration-mode loop (read_history=True) must NOT call the post dispatcher."""
    await store.save(_loop(read_history=True))
    iteration_calls: list[Automation] = []
    post_calls: list[Automation] = []

    async def iteration(auto: Automation) -> str | None:
        iteration_calls.append(auto)
        return "iter-id"

    async def post(auto: Automation) -> str | None:
        post_calls.append(auto)
        return "posted text"

    sched = Scheduler(store=store, build_deps=lambda: None)
    sched.set_iteration_dispatcher(iteration)
    sched.set_post_dispatcher(post)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert post_calls == []
    assert len(iteration_calls) == 1


@pytest.mark.asyncio
async def test_post_mode_without_dispatcher_does_not_increment(store: AutomationStore):
    await store.save(_loop(read_history=False))
    sched = Scheduler(store=store, build_deps=lambda: None)  # no dispatcher of either kind

    await sched._tick()
    for t in list(sched._running):
        await t

    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 0


@pytest.mark.asyncio
async def test_post_mode_max_iterations_disables(store: AutomationStore):
    await store.save(
        _loop(read_history=False, max_iterations=2, iteration_count=1),
    )
    sched, dispatched, _results = _make_post_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 2
    assert reloaded.enabled is False


@pytest.mark.asyncio
async def test_post_mode_fire_gate_defers_while_session_busy(store: AutomationStore):
    await store.save(_loop(read_history=False))
    sched, dispatched, _results = _make_post_scheduler(store)
    sched.set_loop_fire_gate(lambda _auto: False)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert dispatched == []
    reloaded = await store.get("loop-1")
    assert reloaded.iteration_count == 0


@pytest.mark.asyncio
async def test_post_mode_handle_run_completed_fires_due_loop(store: AutomationStore):
    from ntrp.events.internal import RunCompleted

    await store.save(_loop(read_history=False, session_id="sess-post"))
    sched, dispatched, _results = _make_post_scheduler(store)

    await sched.handle_run_completed(
        RunCompleted(run_id="run-x", session_id="sess-post", messages=(), usage=Usage(), result=None),
    )
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_post_mode_aged_out_disables_without_firing(store: AutomationStore):
    old = datetime.now(UTC) - timedelta(days=8)
    loop = Automation(
        task_id="loop-old-post",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=old,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="sess",
        loop_prompt="check x",
        max_age_days=7,
        read_history=False,
        thread_id="sess",
    )
    await store.save(loop)
    sched, dispatched, _results = _make_post_scheduler(store)

    await sched._tick()
    for t in list(sched._running):
        await t

    assert dispatched == []
    reloaded = await store.get("loop-old-post")
    assert reloaded.enabled is False


# ---------------------------------------------------------------------------
# Integration: full post mode flow with a real SessionService — the agent's
# result must land in the target session as an assistant message.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_mode_persists_assistant_message_to_target_session(
    store: AutomationStore, tmp_path: Path
):
    """End-to-end: the post dispatcher's return value must be saved as a
    role='assistant' message in the target session's history."""
    from ntrp.context.models import SessionData
    from ntrp.context.store import SessionStore
    from ntrp.services.session import SessionService

    # Tmp session DB.
    session_conn = await database.connect(tmp_path / "sessions.db")
    session_store = SessionStore(session_conn)
    await session_store.init_schema()
    session_service = SessionService(session_store)

    # Seed an empty session for the post-mode automation to write into.
    state = session_service.create()
    state.session_id = "sess-post-target"
    await session_service.save(state, [])

    await store.save(
        _loop(
            session_id="sess-post-target",
            thread_id="sess-post-target",
            read_history=False,
        ),
    )

    # Post dispatcher: emulate what app.py wires — run agent, append assistant
    # message into target session, return text.
    async def post_dispatcher(auto: Automation) -> str | None:
        result_text = f"hello from {auto.task_id}"
        loaded = await session_service.load(auto.thread_id)
        assert loaded is not None
        loaded.messages.append({"role": "assistant", "content": result_text})
        await session_service.save_progress(loaded.state, loaded.messages)
        return result_text

    sched = Scheduler(store=store, build_deps=lambda: None)
    sched.set_post_dispatcher(post_dispatcher)

    await sched._tick()
    for t in list(sched._running):
        await t

    final: SessionData | None = await session_service.load("sess-post-target")
    assert final is not None
    assistant_msgs = [m for m in final.messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0]["content"] == "hello from loop-1"

    await session_conn.close()


# ---------------------------------------------------------------------------
# Code-review fixes: per-session write lock + fire-gate / dispatcher priority
# alignment for `thread_id` over the legacy `target_session_id`.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_post_dispatches_serialize_under_session_lock():
    """Two concurrent post-mode dispatches against the same target session
    must serialize: their critical sections (load → agent → save) must not
    overlap. Replicates the lock pattern wired in app.py's `_dispatch_post`."""
    import asyncio

    from ntrp.server.app import _get_or_create_session_lock

    locks: dict[str, asyncio.Lock] = {}
    timeline: list[tuple[str, str]] = []  # (event, dispatch_id)

    async def post_dispatch(dispatch_id: str, target_id: str) -> None:
        async with _get_or_create_session_lock(locks, target_id):
            timeline.append(("enter", dispatch_id))
            # Simulate agent run + load + save_progress under the lock.
            await asyncio.sleep(0.05)
            timeline.append(("exit", dispatch_id))

    # Two concurrent dispatches against the same session.
    await asyncio.gather(
        post_dispatch("A", "sess-shared"),
        post_dispatch("B", "sess-shared"),
    )

    # Must be enter/exit/enter/exit (serialized), never enter/enter/exit/exit.
    assert len(timeline) == 4
    assert timeline[0][0] == "enter"
    assert timeline[1] == ("exit", timeline[0][1])
    assert timeline[2][0] == "enter"
    assert timeline[2][1] != timeline[0][1]
    assert timeline[3] == ("exit", timeline[2][1])


@pytest.mark.asyncio
async def test_session_lock_is_per_session_not_global():
    """Two dispatches against DIFFERENT sessions must NOT serialize — the
    lock map is per-session, so they should run in parallel."""
    import asyncio

    from ntrp.server.app import _get_or_create_session_lock

    locks: dict[str, asyncio.Lock] = {}
    overlap = {"yes": False}
    active = {"count": 0}

    async def post_dispatch(target_id: str) -> None:
        async with _get_or_create_session_lock(locks, target_id):
            active["count"] += 1
            if active["count"] > 1:
                overlap["yes"] = True
            await asyncio.sleep(0.05)
            active["count"] -= 1

    await asyncio.gather(
        post_dispatch("sess-A"),
        post_dispatch("sess-B"),
    )

    assert overlap["yes"] is True


def test_loop_target_id_prefers_thread_id_over_legacy_session_id():
    """The fire gate and post dispatcher must agree on the target session.
    `thread_id` (new) wins; `target_session_id` (legacy) is the fallback."""
    from ntrp.server.app import _loop_target_id

    auto = _loop(session_id="legacy-B", thread_id="new-A")
    assert auto.thread_id == "new-A"
    assert auto.target_session_id == "legacy-B"
    # The write target IS thread_id, so the gate must check thread_id too.
    assert _loop_target_id(auto) == "new-A"


def test_loop_target_id_falls_back_to_target_session_id():
    from ntrp.server.app import _loop_target_id

    # No thread_id (legacy row) → fall back to target_session_id.
    auto = Automation(
        task_id="t",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=datetime.now(UTC),
        next_run_at=None,
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id="legacy-only",
        loop_prompt="x",
        thread_id=None,
    )
    assert _loop_target_id(auto) == "legacy-only"


def test_loop_target_id_returns_none_when_both_unset():
    from ntrp.server.app import _loop_target_id

    auto = Automation(
        task_id="t",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=datetime.now(UTC),
        next_run_at=None,
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="loop",
        target_session_id=None,
        loop_prompt="x",
        thread_id=None,
    )
    assert _loop_target_id(auto) is None


# ---------------------------------------------------------------------------
# Channel-aware automations: a row created via `svc.create(thread_id=...,
# read_history=False)` has kind="automation" (not "loop") but is still
# session-bound. The scheduler must route it through the post dispatcher,
# not the standalone agent path.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_thread_id_routes_through_post_dispatcher(store: AutomationStore):
    """A `kind="automation"` row with thread_id + read_history=False MUST flow
    through the post dispatcher — not _run_agent. This is the bug surfaced by
    the Task 9 e2e test: `service.create(thread_id=X, read_history=False)`
    silently routed to _run_agent because the scheduler discriminator was
    `kind == "loop"`."""
    sched, dispatched, _results = _make_post_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)

    auto = await svc.create(
        name="channel-watcher",
        description="post into channel",
        trigger_type="time",
        every="5m",
        thread_id="sess-channel",
        read_history=False,
    )
    assert auto is not None
    assert auto.kind == "automation"  # NOT "loop"
    assert auto.thread_id == "sess-channel"
    # svc.create populates loop_prompt from description for session-bound
    # automations so they can flow through the post dispatcher.
    assert auto.loop_prompt == "post into channel"

    # Force next_run_at into the past so _tick picks it up immediately.
    await store.set_next_run(auto.task_id, datetime.now(UTC) - timedelta(seconds=1))

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1, (
        "channel automation must route to post dispatcher"
    )
    assert dispatched[0].task_id == auto.task_id
    assert dispatched[0].thread_id == "sess-channel"


@pytest.mark.asyncio
async def test_handle_run_completed_fires_kind_automation_with_thread_id(
    store: AutomationStore,
):
    """The run-completed fast-path must catch session-bound automations
    regardless of `kind` — they're identified by thread_id/target_session_id."""
    from ntrp.events.internal import RunCompleted

    now = datetime.now(UTC)
    auto = Automation(
        task_id="channel-auto",
        name="x",
        description="x",
        model=None,
        triggers=[TimeTrigger(every="5m")],
        enabled=True,
        created_at=now,
        next_run_at=now - timedelta(seconds=1),
        last_run_at=None,
        last_result=None,
        running_since=None,
        writable=True,
        kind="automation",
        target_session_id=None,
        loop_prompt="post status",
        thread_id="sess-channel",
        read_history=False,
    )
    await store.save(auto)

    sched, dispatched, _results = _make_post_scheduler(store)

    await sched.handle_run_completed(
        RunCompleted(run_id="run-x", session_id="sess-channel", messages=(), usage=Usage(), result=None),
    )
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    assert dispatched[0].task_id == "channel-auto"


# ---------------------------------------------------------------------------
# Fix coverage: iteration loops created via `svc.create(thread_id=X,
# read_history=True)` (no legacy target_session_id) must fire through the
# iteration dispatcher. Pre-fix, the iteration validation rejected them
# and the dispatcher target resolution returned an empty string.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iteration_loop_with_only_thread_id_fires(store: AutomationStore):
    """`svc.create(thread_id=X, read_history=True)` produces a row with
    thread_id but no target_session_id. The scheduler must accept it as
    a valid iteration-mode loop and route it through the iteration
    dispatcher."""
    sched, dispatched = _make_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)

    auto = await svc.create(
        name="iter-thread-only",
        description="iterate me",
        trigger_type="time",
        every="5m",
        thread_id="sess-new",
        read_history=True,
    )
    assert auto is not None
    assert auto.thread_id == "sess-new"
    assert auto.target_session_id is None
    assert auto.read_history is True

    await store.set_next_run(auto.task_id, datetime.now(UTC) - timedelta(seconds=1))

    await sched._tick()
    for t in list(sched._running):
        await t

    assert len(dispatched) == 1
    assert dispatched[0].task_id == auto.task_id
    assert dispatched[0].thread_id == "sess-new"


@pytest.mark.asyncio
async def test_create_loop_sets_thread_id_and_read_history(store: AutomationStore):
    """`svc.create_loop` must align new rows with the canonical model:
    thread_id is the new home; target_session_id is legacy backfill.
    read_history must be True so the row routes through the iteration
    dispatcher (loops re-enter the session with full history)."""
    sched, _ = _make_scheduler(store)
    svc = AutomationService(store=store, scheduler=sched)

    loop = await svc.create_loop(
        session_id="sess-canon",
        prompt="watch CI",
        every="5m",
    )

    assert loop is not None
    assert loop.thread_id == "sess-canon"
    assert loop.target_session_id == "sess-canon"
    assert loop.read_history is True


@pytest.mark.asyncio
async def test_list_session_bound_excludes_disabled(store: AutomationStore):
    """`list_session_bound_by_session` is consumed by the run-completed
    fast path. Disabled rows shouldn't be hydrated — they'll never fire."""
    enabled_row = _loop(task_id="loop-enabled", session_id="sess-shared")
    disabled_row = _loop(task_id="loop-disabled", session_id="sess-shared")
    await store.save(enabled_row)
    await store.save(disabled_row)
    await store.set_enabled("loop-disabled", False)

    rows = await store.list_session_bound_by_session("sess-shared")
    task_ids = {r.task_id for r in rows}
    assert task_ids == {"loop-enabled"}
