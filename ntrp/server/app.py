import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ntrp.core.agent import Agent
from ntrp.core.events import RunCompleted, RunStarted
from ntrp.core.prompts import INIT_INSTRUCTION
from ntrp.core.spawner import create_spawn_fn
from ntrp.events import (
    AgentResult,
    DoneEvent,
    ErrorEvent,
    SessionInfoEvent,
    TextEvent,
    ThinkingEvent,
)
from ntrp.logging import configure_logging
from ntrp.server.chat import (
    ChatContext,
    expand_skill_command,
    prepare_messages,
    resolve_session,
)
from ntrp.server.routers.dashboard import router as dashboard_router
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.schedule import router as schedule_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import get_run_registry, get_runtime, get_runtime_async, reset_runtime
from ntrp.server.state import RunStatus
from ntrp.server.stream import run_agent_loop, to_sse
from ntrp.tools.core.context import ToolContext

INIT_AUTO_APPROVE = {"remember", "forget"}


class ChatRequest(BaseModel):
    message: str
    skip_approvals: bool = False


class ToolResultRequest(BaseModel):
    run_id: str
    tool_id: str
    result: str
    approved: bool = True


class CancelRequest(BaseModel):
    run_id: str


class ChoiceResultRequest(BaseModel):
    run_id: str
    tool_id: str
    selected: list[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_runtime_async()
    configure_logging()
    yield
    await reset_runtime()


app = FastAPI(
    title="ntrp",
    description="Personal entropy reduction system - API server",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthMiddleware:
    """Pure ASGI middleware — doesn't buffer streaming responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        runtime = get_runtime()
        if runtime.config.api_key and request.url.path != "/health":
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {runtime.config.api_key}":
                response = JSONResponse(status_code=401, content={"detail": "Unauthorized"})
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


app.add_middleware(AuthMiddleware)


app.include_router(dashboard_router)
app.include_router(data_router)
app.include_router(gmail_router)
app.include_router(schedule_router)
app.include_router(session_router)
app.include_router(skills_router)


@app.get("/health")
async def health():
    runtime = get_runtime()
    return {"status": "ok" if runtime._connected else "unavailable"}


@app.get("/index/status")
async def get_index_status():
    runtime = get_runtime()
    return await runtime.get_index_status()


@app.post("/index/start")
async def start_indexing():
    runtime = get_runtime()
    runtime.start_indexing()
    return {"status": "started"}


@app.get("/tools")
async def list_tools():
    runtime = get_runtime()
    tools = []
    for tool in runtime.executor.registry.tools.values():
        tools.append(tool.get_metadata())
    return {"tools": tools}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    runtime = get_runtime()
    registry = get_run_registry()

    session_data = await resolve_session(runtime)
    session_state = session_data.state
    messages = session_data.messages
    session_id = session_state.session_id

    user_message = request.message
    is_init = user_message.strip().lower() == "/init"
    if is_init:
        user_message = INIT_INSTRUCTION
    elif runtime.skill_registry:
        user_message, _ = expand_skill_command(user_message, runtime.skill_registry)

    messages, system_prompt = await prepare_messages(
        runtime, messages, user_message, last_activity=session_state.last_activity
    )

    run = registry.create_run(session_id)
    run.messages = messages
    run.status = RunStatus.RUNNING

    async def event_generator() -> AsyncGenerator[str]:
        ctx = ChatContext(
            runtime=runtime,
            run=run,
            session_state=session_state,
            messages=messages,
            user_message=user_message,
            is_init=is_init,
        )
        run.approval_queue = asyncio.Queue()
        run.choice_queue = asyncio.Queue()

        extra_auto_approve = INIT_AUTO_APPROVE if is_init else set()
        session_state.skip_approvals = request.skip_approvals
        tool_ctx = ToolContext(
            session_state=session_state,
            registry=runtime.executor.registry,
            memory=runtime.memory,
            approval_queue=run.approval_queue,
            choice_queue=run.choice_queue,
            channel=runtime.channel,
            run_id=run.run_id,
            extra_auto_approve=extra_auto_approve,
        )

        yield to_sse(
            SessionInfoEvent(
                session_id=session_id,
                run_id=run.run_id,
                sources=runtime.get_available_sources(),
                source_errors=runtime.get_source_errors(),
                skip_approvals=request.skip_approvals,
            )
        )

        yield to_sse(ThinkingEvent(status="processing..."))
        runtime.channel.publish(RunStarted(run_id=run.run_id, session_id=session_id))

        agent: Agent | None = None
        result: str | None = None
        try:
            tool_ctx.spawn_fn = create_spawn_fn(
                executor=runtime.executor,
                model=runtime.config.chat_model,
                max_depth=runtime.max_depth,
                current_depth=0,
                cancel_check=lambda: run.cancelled,
            )

            agent = Agent(
                tools=runtime.tools,
                tool_executor=runtime.executor,
                model=runtime.config.chat_model,
                system_prompt=system_prompt,
                ctx=tool_ctx,
                max_depth=runtime.max_depth,
                current_depth=0,
                cancel_check=lambda: run.cancelled,
            )

            async for sse in run_agent_loop(ctx, agent, user_message):
                if isinstance(sse, AgentResult):
                    result = sse.text
                else:
                    yield sse

            if result is None:
                return  # Cancelled — session saved in finally

            if result:
                yield to_sse(TextEvent(content=result))

            run.prompt_tokens = agent.total_input_tokens
            run.completion_tokens = agent.total_output_tokens

            yield to_sse(DoneEvent(run_id=run.run_id, usage=asdict(run.get_usage())))
            registry.complete_run(run.run_id)

        except Exception as e:
            yield to_sse(ErrorEvent(message=str(e), recoverable=False))
            run.status = RunStatus.ERROR

        finally:
            if agent:
                run.prompt_tokens = agent.total_input_tokens
                run.completion_tokens = agent.total_output_tokens
                run.messages = agent.messages
            session_state.last_activity = datetime.now(UTC)
            metadata = {"last_input_tokens": agent._last_input_tokens} if agent else None
            await runtime.save_session(session_state, run.messages, metadata=metadata)
            runtime.channel.publish(
                RunCompleted(
                    run_id=run.run_id,
                    prompt_tokens=run.prompt_tokens,
                    completion_tokens=run.completion_tokens,
                    result=result or "",
                )
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/tools/result")
async def submit_tool_result(request: ToolResultRequest):
    registry = get_run_registry()
    run = registry.get_run(request.run_id)

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


@app.post("/tools/choice")
async def submit_choice_result(request: ChoiceResultRequest):
    registry = get_run_registry()
    run = registry.get_run(request.run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.choice_queue:
        await run.choice_queue.put({"selected": request.selected})
    else:
        raise HTTPException(status_code=400, detail="No active stream for this run")

    return {"status": "ok"}


@app.post("/cancel")
async def cancel_run(request: CancelRequest):
    registry = get_run_registry()
    registry.cancel_run(request.run_id)
    return {"status": "cancelled"}
