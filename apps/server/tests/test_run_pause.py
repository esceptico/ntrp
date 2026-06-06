import asyncio

from ntrp.server.state import RunRegistry, RunStatus


async def test_pause_blocks_step_boundary_until_resume():
    registry = RunRegistry()
    run = registry.create_run("sess-pause")

    assert registry.pause_run(run.run_id) == {"found": True, "paused": True}
    assert run.paused is True

    waiter = asyncio.create_task(run.wait_while_paused())
    await asyncio.sleep(0.02)
    assert not waiter.done()  # blocked while paused

    assert registry.resume_run(run.run_id) == {"found": True, "resumed": True}
    await asyncio.wait_for(waiter, timeout=1)  # released on resume
    assert run.paused is False


async def test_wait_returns_immediately_when_not_paused():
    run = RunRegistry().create_run("sess-x")
    await asyncio.wait_for(run.wait_while_paused(), timeout=1)


async def test_cancel_interrupts_a_paused_wait():
    run = RunRegistry().create_run("sess-c")
    run.pause()
    waiter = asyncio.create_task(run.wait_while_paused())
    await asyncio.sleep(0.02)
    waiter.cancel()
    try:
        await waiter
        raise AssertionError("paused wait should surface CancelledError")
    except asyncio.CancelledError:
        pass


def test_pause_is_noop_when_cancelled_or_terminal():
    registry = RunRegistry()
    cancelled = registry.create_run("sess-cancelled")
    cancelled.cancelled = True
    assert cancelled.pause() is False

    done = registry.create_run("sess-done")
    done.status = RunStatus.COMPLETED
    assert done.pause() is False


def test_registry_pause_resume_unknown_run():
    registry = RunRegistry()
    assert registry.pause_run("nope") == {"found": False, "paused": False}
    assert registry.resume_run("nope") == {"found": False, "resumed": False}


def test_resume_without_pause_is_noop():
    run = RunRegistry().create_run("sess-r")
    assert run.resume() is False
    assert run.paused is False
