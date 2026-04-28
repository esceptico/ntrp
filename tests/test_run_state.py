from ntrp.server.state import RunState


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
