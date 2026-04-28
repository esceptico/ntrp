import asyncio
import signal
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib.metadata import version

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from ntrp.server.bus import BusRegistry
from ntrp.server.deps import (
    require_automation_runtime,
    require_knowledge_runtime,
    require_tool_executor,
)
from ntrp.server.middleware import AuthMiddleware, _extract_bearer_token
from ntrp.server.routers.automation import router as automation_router
from ntrp.server.routers.chat import router as chat_router
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.mcp import router as mcp_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.settings import router as settings_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.runtime.automation import AutomationRuntime
from ntrp.server.runtime.knowledge import KnowledgeRuntime
from ntrp.server.schemas import (
    HealthResponse,
    OutboxPruneResponse,
    OutboxReplayResponse,
    OutboxStatusResponse,
    ReplayOutboxRequest,
    SchedulerStatusResponse,
)
from ntrp.settings import verify_api_key
from ntrp.tools.executor import ToolExecutor


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
    bus_registry = BusRegistry()
    runtime.scheduler.set_bus_registry(bus_registry)
    await runtime.start_scheduler()
    runtime.start_monitor()
    app.state.runtime = runtime
    app.state.bus_registry = bus_registry
    _install_shutdown_handlers(runtime, bus_registry)

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
app.include_router(chat_router)
app.include_router(session_router)
app.include_router(settings_router)
app.include_router(skills_router)
app.include_router(mcp_router)


@app.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
async def health(request: Request, runtime: Runtime = Depends(get_runtime)):
    result: dict = {
        "status": "ok" if runtime.connected else "unavailable",
        "version": app.version,
        "has_providers": runtime.config.has_any_model,
        "outbox": await runtime.get_outbox_health(),
    }
    token = _extract_bearer_token(request)
    if token and runtime.config.api_key_hash:
        result["auth"] = verify_api_key(token, runtime.config.api_key_hash)
    return result


@app.get("/outbox/status", response_model=OutboxStatusResponse)
async def get_outbox_status(automation: AutomationRuntime = Depends(require_automation_runtime)):
    return await automation.get_outbox_status()


@app.post("/outbox/dead/replay", response_model=OutboxReplayResponse)
async def replay_outbox_dead_events(
    request: ReplayOutboxRequest,
    automation: AutomationRuntime = Depends(require_automation_runtime),
):
    return await automation.replay_outbox_dead_events(request.event_ids)


@app.delete("/outbox/completed", response_model=OutboxPruneResponse)
async def prune_outbox_completed(
    older_than_days: int = Query(default=7, ge=1, le=3650),
    limit: int = Query(default=1000, ge=1, le=10000),
    automation: AutomationRuntime = Depends(require_automation_runtime),
):
    before = datetime.now(UTC) - timedelta(days=older_than_days)
    result = await automation.prune_outbox_completed(before=before, limit=limit)
    return {**result, "older_than_days": older_than_days}


@app.get("/index/status")
async def get_index_status(knowledge: KnowledgeRuntime = Depends(require_knowledge_runtime)):
    return await knowledge.get_index_status()


@app.get("/scheduler/status", response_model=SchedulerStatusResponse, response_model_exclude_none=True)
async def get_scheduler_status(automation: AutomationRuntime = Depends(require_automation_runtime)):
    return await automation.get_scheduler_status()


@app.post("/index/start")
async def start_indexing(knowledge: KnowledgeRuntime = Depends(require_knowledge_runtime)):
    knowledge.start_indexing()
    return {"status": "started"}


@app.get("/tools")
async def list_tools(executor: ToolExecutor = Depends(require_tool_executor)):
    return {"tools": executor.get_tool_metadata()}
