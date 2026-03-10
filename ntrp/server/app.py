import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from ntrp.config import verify_api_key
from ntrp.server.bus import BusRegistry
from ntrp.server.routers.automation import router as automation_router
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.mcp import router as mcp_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import CancelRequest, ChatRequest, ToolResultRequest
from ntrp.services.chat import prepare_chat, run_chat

SSE_KEEPALIVE = ":\n\n"
KEEPALIVE_INTERVAL = 5


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = Runtime()
    await runtime.connect()
    runtime.start_indexing()
    runtime.start_scheduler()
    runtime.start_monitor()
    runtime.start_consolidation()
    app.state.runtime = runtime
    app.state.bus_registry = BusRegistry()

    yield

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


def _extract_bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    return ""


class AuthMiddleware:
    """Pure ASGI middleware — doesn't buffer streaming responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        runtime: Runtime | None = getattr(request.app.state, "runtime", None)
        if not runtime:
            await self.app(scope, receive, send)
            return

        public_paths = {"/health"}
        if request.url.path not in public_paths:
            token = _extract_bearer_token(request)
            if not token:
                detail = "Missing API key. Include Authorization: Bearer <key> header."
            elif not runtime.config.api_key_hash:
                detail = "No API key configured. Restart server to generate one."
            elif not verify_api_key(token, runtime.config.api_key_hash):
                detail = "Invalid API key. Run 'ntrp serve --reset-key' to generate a new one."
            else:
                detail = None
            if detail:
                response = JSONResponse(status_code=401, content={"detail": detail})
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


app.add_middleware(AuthMiddleware)


app.include_router(data_router)
app.include_router(gmail_router)
app.include_router(automation_router)
app.include_router(session_router)
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


# --- Persistent SSE event stream ---


class SSEStreamingResponse(StreamingResponse):
    """StreamingResponse that skips listen_for_disconnect task group.

    Starlette's default __call__ spawns a parallel listen_for_disconnect
    task when ASGI spec < 2.4 (uvicorn HTTP reports 2.3). On shutdown,
    cancelling that task produces noisy CancelledError tracebacks and
    blocks uvicorn's graceful exit. We skip it — our generator handles
    its own lifecycle via CancelledError.
    """

    async def __call__(self, scope, receive, send):
        try:
            await self.stream_response(send)
        except OSError:
            pass
        if self.background is not None:
            await self.background()


async def _event_stream(session_id: str, bus_registry: BusRegistry) -> AsyncGenerator[str]:
    bus = bus_registry.get_or_create(session_id)
    queue = bus.subscribe()
    last_event_at = time.monotonic()
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
                break
            last_event_at = time.monotonic()
            yield event.to_sse_string()
    except asyncio.CancelledError:
        pass
    finally:
        bus.unsubscribe(queue)


@app.get("/chat/events/{session_id}")
async def chat_events(session_id: str, buses: BusRegistry = Depends(_get_bus_registry)):
    return SSEStreamingResponse(
        _event_stream(session_id, buses),
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

    # If agent is already running, queue message for safe injection
    active_run = runtime.run_registry.get_active_run(session_id)
    if active_run:
        active_run.inject_queue.append({"role": "user", "content": request.message})
        return {"run_id": active_run.run_id, "session_id": session_id}

    try:
        ctx = await prepare_chat(runtime, request.message, request.skip_approvals, session_id=session_id)
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
