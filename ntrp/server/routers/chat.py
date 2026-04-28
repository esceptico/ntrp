import asyncio
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException

from ntrp.events.sse import BackgroundTaskEvent, TextDeltaEvent, TextEvent, TextMessageEndEvent, TextMessageStartEvent
from ntrp.server.bus import BusRegistry
from ntrp.server.deps import get_bus_registry, require_run_registry
from ntrp.server.middleware import SSEStreamingResponse
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    BackgroundRequest,
    CancelRequest,
    ChatRequest,
    ChatRunsStatusResponse,
    ToolResultRequest,
)
from ntrp.server.state import RunRegistry, RunStatus
from ntrp.services.chat import submit_chat_message

router = APIRouter(tags=["chat"])

SSE_KEEPALIVE = ":\n\n"
KEEPALIVE_INTERVAL = 5


async def _event_stream(
    session_id: str, bus_registry: BusRegistry, run_registry: RunRegistry, stream: bool = False
) -> AsyncGenerator[str]:
    bus = bus_registry.get_or_create(session_id)
    queue = bus.subscribe()
    last_event_at = time.monotonic()

    # Transform state: wrap TextDelta/Text sequences in Start/End boundaries.
    # Inspired by AG-UI's transformChunks pattern.
    in_text_message = False
    msg_counter = 0

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                if time.monotonic() - last_event_at >= KEEPALIVE_INTERVAL:
                    last_event_at = time.monotonic()
                    yield SSE_KEEPALIVE
                continue

            if event is None:
                if in_text_message:
                    yield TextMessageEndEvent(message_id=f"msg-{msg_counter}").to_sse_string()
                break

            is_text = isinstance(event, TextDeltaEvent | TextEvent)
            is_passthrough = isinstance(event, BackgroundTaskEvent)

            if is_text and not in_text_message:
                msg_counter += 1
                in_text_message = True
                last_event_at = time.monotonic()
                yield TextMessageStartEvent(message_id=f"msg-{msg_counter}").to_sse_string()
                await asyncio.sleep(0)
            elif not is_text and not is_passthrough and in_text_message:
                in_text_message = False
                last_event_at = time.monotonic()
                yield TextMessageEndEvent(message_id=f"msg-{msg_counter}").to_sse_string()
                await asyncio.sleep(0)

            if not stream and isinstance(event, TextDeltaEvent):
                continue

            last_event_at = time.monotonic()
            yield event.to_sse_string()
            # Yield to event loop so the transport flushes each event
            # individually instead of batching them in the TCP buffer.
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        pass
    finally:
        bus.unsubscribe(queue)
        if not bus._subscribers and not run_registry.get_active_run(session_id):
            bus_registry.remove(session_id)


@router.get("/chat/events/{session_id}")
async def chat_events(
    session_id: str,
    stream: bool = False,
    buses: BusRegistry = Depends(get_bus_registry),
    run_registry: RunRegistry = Depends(require_run_registry),
):
    return SSEStreamingResponse(
        _event_stream(session_id, buses, run_registry, stream=stream),
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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/inject/{client_id}")
async def cancel_inject(
    client_id: str,
    session_id: str,
    run_registry: RunRegistry = Depends(require_run_registry),
):
    active_run = run_registry.get_active_run(session_id)
    if active_run is None:
        raise HTTPException(status_code=404, detail="No active run")

    if active_run.cancel_injection(client_id):
        return {"status": "cancelled", "client_id": client_id}

    raise HTTPException(status_code=409, detail="Already ingested")


@router.post("/tools/result")
async def submit_tool_result(request: ToolResultRequest, run_registry: RunRegistry = Depends(require_run_registry)):
    run = run_registry.get_run(request.run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.approval_queue:
        await run.approval_queue.put(
            {
                "type": "tool_response",
                "tool_id": request.tool_id,
                "result": request.result,
                "approved": request.approved,
            }
        )
    else:
        raise HTTPException(status_code=400, detail="No active stream for this run")

    return {"status": "ok"}


@router.post("/cancel")
async def cancel_run(request: CancelRequest, run_registry: RunRegistry = Depends(require_run_registry)):
    run_registry.cancel_run(request.run_id)
    return {"status": "cancelled"}


@router.post("/chat/background")
async def background_run(request: BackgroundRequest, run_registry: RunRegistry = Depends(require_run_registry)):
    run = run_registry.get_run(request.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != RunStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Run is not active")
    run.backgrounded = True
    return {"status": "backgrounding"}


@router.get("/chat/background-tasks")
async def list_background_tasks(session_id: str, run_registry: RunRegistry = Depends(require_run_registry)):
    registry = run_registry.get_background_registry(session_id)
    pending = registry.list_pending()
    return {"tasks": [{"task_id": tid, "command": cmd} for tid, cmd in pending]}


@router.post("/chat/background-tasks/{task_id}/cancel")
async def cancel_background_task(
    task_id: str,
    session_id: str,
    run_registry: RunRegistry = Depends(require_run_registry),
):
    registry = run_registry.get_background_registry(session_id)
    command = registry.cancel(task_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Task not found or already done")
    return {"status": "cancelled", "task_id": task_id}
