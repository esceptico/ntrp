from datetime import UTC, datetime, timedelta

from ntrp.server.state import RunRegistry, RunState, RunStatus


def test_run_state_owns_injection_queue_lifecycle():
    run = RunState(run_id="run-1", session_id="sess-1")

    run.queue_injection({"role": "user", "content": "first", "client_id": "cid-1"})
    run.queue_injection({"role": "user", "content": "second", "client_id": "cid-2"})

    assert run.pending_injection_count == 2
    assert run.cancel_injection("cid-1") is True
    assert run.cancel_injection("missing") is False

    assert run.drain_injections() == [{"role": "user", "content": "second", "client_id": "cid-2"}]
    assert run.pending_injection_count == 0
    assert run.drain_injections() == []


def test_run_state_queues_injection_batches():
    run = RunState(run_id="run-1", session_id="sess-1")

    run.queue_injections([])
    run.queue_injections(
        [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ]
    )

    assert run.drain_injections() == [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
    ]


def test_run_state_status_is_content_free():
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    run = RunState(
        run_id="run-1",
        session_id="sess-1",
        created_at=now - timedelta(seconds=30),
        updated_at=now - timedelta(seconds=5),
    )
    run.messages = [{"role": "user", "content": "do not leak this"}]
    run.queue_injection({"role": "user", "content": "queued secret", "client_id": "cid-1"})
    run.updated_at = now - timedelta(seconds=5)

    status = run.get_status(now)

    assert status["message_count"] == 1
    assert status["pending_injections"] == 1
    assert status["age_seconds"] == 30
    assert status["idle_seconds"] == 5
    assert "messages" not in status
    assert "content" not in status


def test_run_registry_status_reports_active_runs_only():
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    registry = RunRegistry()
    active = registry.create_run("sess-active")
    active.status = RunStatus.RUNNING
    active.queue_injection({"role": "user", "content": "queued"})

    stale = registry.create_run("sess-stale")
    stale.status = RunStatus.COMPLETED

    status = registry.get_status(now)

    assert status["observed_at"] == now.isoformat()
    assert status["total_retained"] == 2
    assert status["active_count"] == 1
    assert registry.active_run_count == 1
    assert status["active_runs"][0]["run_id"] == active.run_id
    assert status["active_runs"][0]["pending_injections"] == 1
    assert status["background_task_sessions"] == []
