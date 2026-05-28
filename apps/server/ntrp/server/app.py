import asyncio
import signal
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ntrp.agent import Role
from ntrp.automation.models import Automation
from ntrp.automation.prompts import AUTOMATION_PROMPT, AUTOMATION_SUFFIX
from ntrp.automation.scheduler import AUTOMATION_BUS_KEY
from ntrp.operator.runner import RunRequest, run_agent, run_agent_streaming
from ntrp.server.bus import BusRegistry, prime_bus_cursor_from_store
from ntrp.server.middleware import AuthMiddleware
from ntrp.server.routers.admin_memory import router as admin_memory_router
from ntrp.server.routers.automation import router as automation_router
from ntrp.server.routers.chat import router as chat_router
from ntrp.server.routers.context import router as context_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.loops import router as loops_router
from ntrp.server.routers.mcp import router as mcp_router
from ntrp.server.routers.ops import router as ops_router
from ntrp.server.routers.providers import router as providers_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.settings import router as settings_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import Runtime
from ntrp.services.chat import submit_chat_message


def _loop_target_id(automation: Automation) -> str | None:
    """Resolve the session id a loop targets for writes/gating.

    `thread_id` (new field) wins; `target_session_id` is the legacy
    fallback. Used by both `_dispatch_post` and `_loop_can_fire` so the
    fire gate always checks the same session the post writer will write
    into.
    """
    return automation.thread_id or automation.target_session_id


def _get_or_create_session_lock(locks: dict[str, asyncio.Lock], session_id: str) -> asyncio.Lock:
    lock = locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        locks[session_id] = lock
    return lock


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
    bus_registry = BusRegistry(
        record_event=runtime.session_service.store.record_session_event if runtime.session_service else None,
    )
    runtime.scheduler.set_bus_registry(bus_registry)

    # Per-session write locks. The post dispatcher holds one for its full
    # lifetime so two concurrent post-mode dispatches against the same
    # target session can't trample each other's tail-end load→save window.
    session_write_locks: dict[str, asyncio.Lock] = {}

    async def _dispatch_session_message(
        session_id: str,
        message: str,
        client_id: str | None = None,
        skip_approvals: bool | None = False,
    ) -> str | None:
        result = await submit_chat_message(
            runtime.run_registry,
            lambda: runtime.build_chat_deps(),
            bus_registry,
            message=message,
            session_id=session_id,
            skip_approvals=skip_approvals,
            client_id=client_id,
            session_service=runtime.session_service,
        )
        return result.get("run_id") if isinstance(result, dict) else None

    async def _dispatch_iteration(automation: Automation) -> str | None:
        # Iteration loops are autonomous: the user already approved the
        # loop at creation (via the create_loop approval card), so
        # subsequent iterations should skip per-tool approvals. Matches
        # the same writable→skip_approvals convention the regular
        # automation path uses in scheduler._run_agent.
        return await _dispatch_session_message(
            _loop_target_id(automation) or "",
            automation.loop_prompt or "",
            client_id=f"loop:{automation.task_id}:{automation.iteration_count + 1}",
            skip_approvals=automation.writable,
        )

    runtime.scheduler.set_iteration_dispatcher(_dispatch_iteration)
    runtime.dispatch_session_message = _dispatch_session_message

    async def _dispatch_post(automation: Automation) -> str | None:
        # Post mode: run the agent fresh (no session history), then write
        # the agent's final text into the target session as an assistant
        # message. The chat UI picks it up on the next history fetch —
        # no live SSE for now (can be wired later if needed).
        #
        # The whole body runs under a per-session write lock so concurrent
        # post-mode dispatches against the same target session serialize
        # their load→save windows. SessionStore also serializes chat save /
        # progress writes per session, so post-vs-chat history writes share
        # the same one-writer-at-a-time model.
        if not runtime.session_service:
            return None
        target_id = _loop_target_id(automation)
        if not target_id:
            return None

        async with _get_or_create_session_lock(session_write_locks, target_id):
            prompt = AUTOMATION_PROMPT.render(description=automation.loop_prompt or "", context=None)
            request = RunRequest(
                prompt=prompt,
                prompt_suffix=AUTOMATION_SUFFIX,
                writable=automation.writable,
                source_id=automation.task_id,
                model=automation.model,
                skip_approvals=automation.writable,
                automation_id=automation.task_id,
            )

            deps = runtime.build_operator_deps()
            if bus_registry:
                event_store = runtime.session_service.store if runtime.session_service else None
                await prime_bus_cursor_from_store(bus_registry, AUTOMATION_BUS_KEY, event_store)
                bus = bus_registry.get_or_create(AUTOMATION_BUS_KEY)
                run_result = await run_agent_streaming(deps, request, bus, automation.task_id)
            else:
                run_result = await run_agent(deps, request)
            text = run_result.output
            if not text:
                return None

            # Append as an assistant message into the target session.
            data = await runtime.session_service.load(target_id)
            if data is None:
                return text
            data.messages.append({"role": Role.ASSISTANT, "content": text})
            await runtime.session_service.save_progress(data.state, data.messages)
            return text

    runtime.scheduler.set_post_dispatcher(_dispatch_post)

    def _loop_can_fire(automation: Automation) -> bool:
        # Skip the tick if the loop's target session has an active user
        # run. Applies to both modes:
        #  • Iteration would queue the loop prompt into the active run's
        #    inject_queue, rendering inside the user's "Worked" collapse
        #    instead of as a fresh chat turn.
        #  • Post would race the in-flight run on session_service writes.
        # handle_run_completed fires deferred loops the moment the
        # session goes idle.
        # Target priority must match _dispatch_post (via _loop_target_id):
        # thread_id (new field) wins over target_session_id (legacy
        # fallback). Otherwise a migrated row with mismatched fields would
        # be gated on one session while the post writes into another.
        target_id = _loop_target_id(automation)
        if not target_id:
            return True
        active = runtime.run_registry.get_accepting_run(target_id)
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

    await bus_registry.close_all()
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


app.include_router(gmail_router)
app.include_router(admin_memory_router)
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
