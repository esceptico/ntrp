import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ntrp.events.sse import KeepaliveEvent, StreamResetEvent, TextDeltaEvent
from ntrp.server.bus import BusRegistry, StreamRecord, stream_record_to_sse_string
from ntrp.server.deps import get_bus_registry, require_run_registry
from ntrp.server.middleware import SSEStreamingResponse
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    BackgroundAgentRunsResponse,
    BackgroundRequest,
    CancelRequest,
    ChatRequest,
    ChatRunsStatusResponse,
    ToolResultRequest,
)
from ntrp.server.state import RunRegistry, RunStatus
from ntrp.services.chat import submit_chat_message

router = APIRouter(tags=["chat"])

KEEPALIVE_INTERVAL = 5


def _keepalive(session_id: str, latest_seq: int) -> str:
    """Typed data frame carrying the bus's latest emitted seq.

    The frame does not allocate a new bus seq; it repeats the latest durable
    cursor so quiet subscribers can advance/confirm their client cursor.
    """
    event = KeepaliveEvent(session_id=session_id, latest_seq=latest_seq)
    sse = event.to_sse()
    payload = {
        **json.loads(sse["data"]),
        "seq": latest_seq,
        "session_id": session_id,
    }
    return f"id: {latest_seq}\nevent: {sse['event']}\ndata: {json.dumps(payload)}\n\n"


async def _bus_for_event_stream(session_id: str, bus_registry: BusRegistry, event_store=None):
    bus = bus_registry.get(session_id)
    if event_store is None:
        return bus or bus_registry.get_or_create(session_id)

    latest_seq = await event_store.get_latest_session_event_seq(session_id)
    if latest_seq:
        checkpoint_seq = await event_store.get_latest_session_checkpoint_seq(session_id)
        # session_events is only a cursor ledger; chat_runs.last_seq is
        # the persisted canonical checkpoint written after save/save_progress.
        bus_registry.remember_session_cursor(
            session_id,
            next_seq=latest_seq + 1,
            checkpoint_seq=checkpoint_seq,
        )
        return bus_registry.get_or_create(session_id)

    return bus or bus_registry.get_or_create(session_id)


async def _event_stream(
    session_id: str,
    bus_registry: BusRegistry,
    run_registry: RunRegistry,
    stream: bool = False,
    after_seq: int | None = None,
    event_store=None,
) -> AsyncGenerator[str]:
    bus = await _bus_for_event_stream(session_id, bus_registry, event_store)
    subscription = bus.subscribe_with_replay(after_seq=after_seq)
    snapshot, queue = subscription
    last_event_at = time.monotonic()

    def should_emit(event) -> bool:
        return stream or not isinstance(event, TextDeltaEvent)

    try:
        if subscription.replay_gap and after_seq is not None:
            newest_seq = bus.next_seq - 1
            reset_seq = min(max(after_seq + 1, bus.checkpoint_seq), newest_seq)
            reset_record = StreamRecord(
                seq=reset_seq,
                session_id=session_id,
                event=StreamResetEvent(reason="replay_gap"),
            )
            yield stream_record_to_sse_string(session_id, reset_record)
            last_event_at = time.monotonic()
            await asyncio.sleep(0)

        for record in snapshot:
            event = record.event
            if not should_emit(event):
                last_event_at = time.monotonic()
                continue
            yield stream_record_to_sse_string(session_id, record, replay=True)
            await asyncio.sleep(0)

        while True:
            try:
                record = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                if time.monotonic() - last_event_at >= KEEPALIVE_INTERVAL:
                    last_event_at = time.monotonic()
                    yield _keepalive(session_id, bus.next_seq - 1)
                continue

            if record is None:
                break

            event = record.event
            if not should_emit(event):
                last_event_at = time.monotonic()
                continue

            last_event_at = time.monotonic()
            yield stream_record_to_sse_string(session_id, record)
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        pass
    finally:
        bus.unsubscribe(queue)
        if not bus._subscribers and not run_registry.get_active_run(session_id):
            await bus_registry.remove_if_idle(
                session_id,
                is_active=lambda: run_registry.get_active_run(session_id) is not None,
            )


@router.get("/chat/events/{session_id}")
async def chat_events(
    session_id: str,
    request: Request,
    stream: bool = False,
    after_seq: Annotated[int | None, Query(ge=0)] = None,
    buses: BusRegistry = Depends(get_bus_registry),
    run_registry: RunRegistry = Depends(require_run_registry),
):
    runtime = getattr(request.app.state, "runtime", None)
    session_service = getattr(runtime, "session_service", None)
    event_store = session_service.store if session_service else None
    return SSEStreamingResponse(
        _event_stream(session_id, buses, run_registry, stream=stream, after_seq=after_seq, event_store=event_store),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/runs/status", response_model=ChatRunsStatusResponse)
async def get_chat_runs_status(run_registry: RunRegistry = Depends(require_run_registry)):
    return run_registry.get_status()


@router.post("/chat/message")
async def chat_message(
    request: ChatRequest,
    runtime: Runtime = Depends(get_runtime),
    buses: BusRegistry = Depends(get_bus_registry),
):
    session_id = request.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    images = [img.model_dump() for img in request.images] if request.images else None
    context = request.context or None

    try:
        return await submit_chat_message(
            runtime.run_registry,
            lambda: runtime.build_chat_deps(),
            buses,
            message=request.message,
            skip_approvals=request.skip_approvals,
            session_id=session_id,
            images=images,
            context=context,
            client_id=request.client_id,
            session_service=getattr(runtime, "session_service", None),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/inject/{client_id}")
async def cancel_inject(
    client_id: str,
    session_id: str,
    run_registry: RunRegistry = Depends(require_run_registry),
    runtime: Runtime = Depends(get_runtime),
):
    active_run = run_registry.get_active_run(session_id)
    if active_run is None:
        raise HTTPException(status_code=404, detail="No active run")

    if active_run.cancel_injection(client_id):
        session_service = getattr(runtime, "session_service", None)
        mark_cancelled = getattr(session_service, "mark_chat_queued_message_cancelled", None)
        if mark_cancelled:
            await mark_cancelled(client_id)
        return {"status": "cancelled", "client_id": client_id}

    raise HTTPException(status_code=409, detail="Already ingested")


@router.post("/tools/result")
async def submit_tool_result(
    request: ToolResultRequest,
    run_registry: RunRegistry = Depends(require_run_registry),
    runtime: Runtime = Depends(get_runtime),
):
    session_service = getattr(runtime, "session_service", None)
    store = getattr(session_service, "store", None)

    async def resolve_durable_approval_if_pending() -> bool:
        if store is None:
            return False
        row = await store.get_tool_approval(run_id=request.run_id, tool_call_id=request.tool_id)
        if row is None:
            return False
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Approval already resolved")
        resolved = await store.resolve_tool_approval(
            run_id=request.run_id,
            tool_call_id=request.tool_id,
            status="approved" if request.approved else "rejected",
            result_feedback=request.result.strip() or None,
        )
        if not resolved:
            raise HTTPException(status_code=409, detail="Approval already resolved")
        return True

    run = run_registry.get_run(request.run_id)

    if not run:
        if await resolve_durable_approval_if_pending():
            return {"status": "ok"}
        raise HTTPException(status_code=404, detail="Run not found")

    future = run.pending_approvals.get(request.tool_id)
    if future is None:
        if await resolve_durable_approval_if_pending():
            return {"status": "ok"}
        raise HTTPException(status_code=404, detail="No pending approval for this tool")
    if future.done():
        raise HTTPException(status_code=409, detail="Approval already resolved")

    durable_row_exists = False
    if store is not None:
        try:
            row = await store.get_tool_approval(run_id=request.run_id, tool_call_id=request.tool_id)
            if row is not None:
                durable_row_exists = True
                if row["status"] != "pending":
                    raise HTTPException(status_code=409, detail="Approval already resolved")
        except HTTPException:
            raise
        except Exception:
            pass

    if future.done():
        raise HTTPException(status_code=409, detail="Approval already resolved")

    future.set_result(
        {
            "type": "tool_response",
            "tool_id": request.tool_id,
            "result": request.result,
            "approved": request.approved,
        }
    )

    if store is not None and durable_row_exists:
        try:
            await store.resolve_tool_approval(
                run_id=request.run_id,
                tool_call_id=request.tool_id,
                status="approved" if request.approved else "rejected",
                result_feedback=request.result.strip() or None,
            )
        except Exception:
            pass

    return {"status": "ok"}


@router.post("/cancel", status_code=202)
async def cancel_run(request: CancelRequest, run_registry: RunRegistry = Depends(require_run_registry)):
    result = run_registry.cancel_run(request.run_id)
    if not result["found"]:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "cancelling", **result}


@router.post("/chat/background")
async def background_run(request: BackgroundRequest, run_registry: RunRegistry = Depends(require_run_registry)):
    run = run_registry.get_run(request.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != RunStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Run is not active")
    run.backgrounded = True
    return {"status": "backgrounding"}


@router.get("/chat/background-tasks", response_model=BackgroundAgentRunsResponse)
async def list_background_tasks(
    session_id: str,
    runtime: Runtime = Depends(get_runtime),
    run_registry: RunRegistry = Depends(require_run_registry),
):
    session_service = getattr(runtime, "session_service", None)
    store = getattr(session_service, "store", None)
    if store is not None:
        return {"tasks": await store.list_background_agent_runs(session_id)}

    registry = run_registry.get_background_registry(session_id)
    pending = registry.list_pending()
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return {
        "tasks": [
            {
                "task_id": tid,
                "session_id": session_id,
                "parent_run_id": None,
                "status": "running",
                "command": cmd,
                "detail": None,
                "result_ref": None,
                "created_at": now,
                "started_at": None,
                "updated_at": now,
                "ended_at": None,
                "cancel_requested_at": None,
                "notified_at": None,
            }
            for tid, cmd in pending
        ]
    }


@router.post("/chat/background-tasks/{task_id}/cancel")
async def cancel_background_task(
    task_id: str,
    session_id: str,
    runtime: Runtime = Depends(get_runtime),
    run_registry: RunRegistry = Depends(require_run_registry),
):
    requested = False
    session_service = getattr(runtime, "session_service", None)
    store = getattr(session_service, "store", None)
    if store is not None:
        requested = await store.request_background_agent_cancel(session_id, task_id)

    registry = run_registry.get_background_registry(session_id)
    command = registry.cancel(task_id)
    if command is None and not requested:
        raise HTTPException(status_code=404, detail="Task not found or already done")
    return {
        "status": "cancelled" if command is not None else "cancel_requested",
        "task_id": task_id,
        "command": command,
    }
