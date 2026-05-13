import asyncio
import signal
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ntrp.automation.models import Automation
from ntrp.server.bus import BusRegistry
from ntrp.server.middleware import AuthMiddleware
from ntrp.server.routers.automation import router as automation_router
from ntrp.server.routers.chat import router as chat_router
from ntrp.server.routers.loops import router as loops_router
from ntrp.services.chat import submit_chat_message
from ntrp.server.routers.context import router as context_router
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.mcp import router as mcp_router
from ntrp.server.routers.ops import router as ops_router
from ntrp.server.routers.providers import router as providers_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.settings import router as settings_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import Runtime


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

    async def _dispatch_loop(automation: Automation) -> str | None:
        # Loops are autonomous: the user already approved the loop at
        # creation (via the create_loop approval card), so subsequent
        # iterations should skip per-tool approvals. Matches the same
        # writable→skip_approvals convention the regular automation path
        # uses in scheduler._run_agent.
        result = await submit_chat_message(
            runtime.run_registry,
            lambda: runtime.build_chat_deps(),
            bus_registry,
            message=automation.loop_prompt or "",
            session_id=automation.target_session_id or "",
            skip_approvals=automation.writable,
            client_id=f"loop:{automation.task_id}:{automation.iteration_count + 1}",
        )
        return result.get("run_id") if isinstance(result, dict) else None

    runtime.scheduler.set_loop_dispatcher(_dispatch_loop)

    def _loop_can_fire(automation: Automation) -> bool:
        # Skip the tick if the loop's target session has an active user
        # run. Otherwise submit_chat_message would queue the loop prompt
        # into the active run's inject_queue, and the iteration renders
        # as content inside the user's "Worked" collapse instead of as a
        # fresh chat turn. handle_run_completed fires deferred loops the
        # moment the session goes idle.
        if not automation.target_session_id:
            return True
        active = runtime.run_registry.get_accepting_run(automation.target_session_id)
        return active is None

    runtime.scheduler.set_loop_fire_gate(_loop_can_fire)
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
app.include_router(context_router)
app.include_router(ops_router)
app.include_router(providers_router)
app.include_router(session_router)
app.include_router(settings_router)
app.include_router(skills_router)
app.include_router(mcp_router)
app.include_router(loops_router)
