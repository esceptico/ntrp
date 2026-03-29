import asyncio
import signal
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from ntrp.events.sse import BackgroundTaskEvent, TextDeltaEvent, TextEvent, TextMessageEndEvent, TextMessageStartEvent
from ntrp.server.bus import BusRegistry
from ntrp.server.middleware import AuthMiddleware, SSEStreamingResponse, _extract_bearer_token
from ntrp.server.routers.automation import router as automation_router
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.mcp import router as mcp_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.settings import router as settings_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import BackgroundRequest, CancelRequest, ChatRequest, ToolResultRequest
from ntrp.server.state import RunRegistry, RunStatus
from ntrp.services.chat import build_user_content, prepare_chat, run_chat
from ntrp.settings import verify_api_key

SSE_KEEPALIVE = ":\n\n"
KEEPALIVE_INTERVAL = 5


def _install_shutdown_handlers(runtime: Runtime, bus_registry: BusRegistry) -> None:
    """Intercept SIGINT/SIGTERM to close SSE streams before uvicorn's timeout.

    Uvicorn waits for HTTP connections to close before running lifespan
    teardown, but SSE streams never finish on their own.  We wrap the
    existing signal handlers to push a sentinel into every SSE queue and
    cancel active runs first, so connections close promptly.
    Pattern from sse-starlette (AppStatus).
    """
    for sig in (signal.SIGINT, signal.SIGTERM):
        original = signal.getsignal(sig)

        def _handler(signum: int, frame, _orig=original) -> None:
            bus_registry.close_all_sync()
            if callable(_orig):
                _orig(signum, frame)

        signal.signal(sig, _handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = Runtime()
    await runtime.connect()
    runtime.start_indexing()
    await runtime.start_scheduler()
    runtime.start_monitor()
    app.state.runtime = runtime
    app.state.bus_registry = BusRegistry()
    _install_shutdown_handlers(runtime, app.state.bus_registry)

    try:
        yield
    except asyncio.CancelledError:
        pass

    await runtime.close()


app = FastAPI(
    title="ntrp",
    description="Personal entropy reduction system - API server",
    version=version("ntrp"),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(AuthMiddleware)


app.include_router(data_router)
app.include_router(gmail_router)
app.include_router(automation_router)
app.include_router(session_router)
app.include_router(settings_router)
app.include_router(skills_router)
app.include_router(mcp_router)


def _get_bus_registry(request: Request) -> BusRegistry:
    return request.app.state.bus_registry


@app.get("/health")
async def health(request: Request, runtime: Runtime = Depends(get_runtime)):
    result: dict = {
        "status": "ok" if runtime.connected else "unavailable",
        "version": app.version,
        "has_providers": runtime.config.has_any_model,
    }
    token = _extract_bearer_token(request)
    if token and runtime.config.api_key_hash:
        result["auth"] = verify_api_key(token, runtime.config.api_key_hash)
    return result


@app.get("/index/status")
async def get_index_status(runtime: Runtime = Depends(get_runtime)):
    return await runtime.get_index_status()


@app.post("/index/start")
async def start_indexing(runtime: Runtime = Depends(get_runtime)):
    runtime.start_indexing()
    return {"status": "started"}


@app.get("/tools")
async def list_tools(runtime: Runtime = Depends(get_runtime)):
    return {"tools": runtime.executor.get_tool_metadata()}


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


@app.get("/chat/events/{session_id}")
async def chat_events(
    session_id: str,
    stream: bool = False,
    buses: BusRegistry = Depends(_get_bus_registry),
    runtime: Runtime = Depends(get_runtime),
):
    return SSEStreamingResponse(
        _event_stream(session_id, buses, runtime.run_registry, stream=stream),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Fire-and-forget message send ---


@app.post("/chat/message")
async def chat_message(
    request: ChatRequest,
    runtime: Runtime = Depends(get_runtime),
    buses: BusRegistry = Depends(_get_bus_registry),
):
    session_id = request.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    images = [img.model_dump() for img in request.images] if request.images else None
    context = request.context or None

    # If agent is already running, queue message for safe injection
    active_run = runtime.run_registry.get_active_run(session_id)
    if active_run:
        active_run.inject_queue.append(
            {"role": "user", "content": build_user_content(request.message, images, context)}
        )
        return {"run_id": active_run.run_id, "session_id": session_id}

    try:
        ctx = await prepare_chat(
            runtime, request.message, request.skip_approvals, session_id=session_id, images=images, context=context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    bus = buses.get_or_create(session_id)
    task = asyncio.create_task(run_chat(ctx, bus))
    ctx.run.task = task

    return {"run_id": ctx.run.run_id, "session_id": ctx.session_state.session_id}


# --- Existing endpoints ---


@app.post("/tools/result")
async def submit_tool_result(request: ToolResultRequest, runtime: Runtime = Depends(get_runtime)):
    run = runtime.run_registry.get_run(request.run_id)

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


@app.post("/cancel")
async def cancel_run(request: CancelRequest, runtime: Runtime = Depends(get_runtime)):
    runtime.run_registry.cancel_run(request.run_id)
    return {"status": "cancelled"}


@app.post("/chat/background")
async def background_run(request: BackgroundRequest, runtime: Runtime = Depends(get_runtime)):
    run = runtime.run_registry.get_run(request.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != RunStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Run is not active")
    run.backgrounded = True
    return {"status": "backgrounding"}


@app.get("/chat/background-tasks")
async def list_background_tasks(session_id: str, runtime: Runtime = Depends(get_runtime)):
    registry = runtime.run_registry.get_background_registry(session_id)
    pending = registry.list_pending()
    return {"tasks": [{"task_id": tid, "command": cmd} for tid, cmd in pending]}


@app.post("/chat/background-tasks/{task_id}/cancel")
async def cancel_background_task(task_id: str, session_id: str, runtime: Runtime = Depends(get_runtime)):
    registry = runtime.run_registry.get_background_registry(session_id)
    command = registry.cancel(task_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Task not found or already done")
    return {"status": "cancelled", "task_id": task_id}
