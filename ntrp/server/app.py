import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ntrp.constants import AGENT_INIT_ITERATIONS
from ntrp.context import sanitize_history_for_model
from ntrp.core.agent import Agent
from ntrp.events import (
    CancelledEvent,
    DoneEvent,
    ErrorEvent,
    SessionInfoEvent,
    SSEEvent,
    TextEvent,
    ThinkingEvent,
)
from ntrp.logging import configure_logging
from ntrp.server.chat import (
    ChatContext,
    prepare_messages,
    resolve_session,
)
from ntrp.server.prompts import INIT_INSTRUCTION
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.runtime import get_runtime, get_runtime_async, reset_runtime
from ntrp.server.state import RunStatus, get_run_registry
from ntrp.tools.core import ToolContext


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    yolo: bool = False


class ToolResultRequest(BaseModel):
    run_id: str
    tool_id: str
    result: str
    approved: bool = True


class CancelRequest(BaseModel):
    run_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Initialize runtime at startup
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

app.include_router(data_router)
app.include_router(gmail_router)
app.include_router(session_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


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


def _to_sse(event: SSEEvent | dict) -> str:
    if isinstance(event, SSEEvent):
        return event.to_sse_string()
    return f"data: {json.dumps(event)}\n\n"


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
        run.event_queue = ctx.client_responses

        extra_auto_approve = {"remember", "forget", "reflect", "merge"} if is_init else set()
        session_state.yolo = request.yolo
        tool_ctx = ToolContext(
            session_state=session_state,
            executor=runtime.executor,
            emit=ctx.event_bus.put,
            approval_queue=ctx.client_responses,
            extra_auto_approve=extra_auto_approve,
        )

        yield _to_sse(
            SessionInfoEvent(
                session_id=session_id,
                run_id=run.run_id,
                sources=runtime.get_available_sources(),
                source_errors=runtime.get_source_errors(),
                yolo=request.yolo,
            )
        )

        yield _to_sse(ThinkingEvent(status="processing..."))

        try:
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

            max_iters = AGENT_INIT_ITERATIONS if is_init else runtime.max_iterations
            result: str | None = None

            async for sse in _run_agent_loop(ctx, agent, user_message, max_iters):
                if isinstance(sse, dict) and "_result" in sse:
                    result = sse["_result"]
                else:
                    yield sse

            # Handle agent result
            if result is None:
                return  # Cancelled

            if result:
                yield _to_sse(TextEvent(content=result))

            run.prompt_tokens = agent.total_input_tokens
            run.completion_tokens = agent.total_output_tokens

            run.messages = agent.messages
            session_state.last_activity = datetime.now()
            await runtime.save_session(session_state, run.messages)

            yield _to_sse(DoneEvent(run_id=run.run_id, usage=run.get_usage()))
            registry.complete_run(run.run_id)

        except Exception as e:
            yield _to_sse(ErrorEvent(message=str(e), recoverable=False))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _run_agent_loop(ctx: ChatContext, agent, user_message: str, max_iterations: int):
    """Run agent and yield SSE strings. Yields dict with result at end.

    Uses a merged event stream pattern:
    - Agent runs in background task, pushing events to a shared queue
    - Subagent/tool events also go to the same queue via event_bus forwarding
    - Consumer yields events as they arrive in true real-time
    """
    raw_history = ctx.messages[:-1] if len(ctx.messages) > 1 else None
    history = sanitize_history_for_model(raw_history) if raw_history else None

    # Sentinel to signal completion
    _DONE = object()
    _ERROR = object()

    # Merged event queue - all events flow here
    merged_queue: asyncio.Queue = asyncio.Queue()
    result: str = ""
    error: Exception | None = None

    async def forward_event_bus():
        """Forward events from event_bus to merged_queue in real-time."""
        while True:
            try:
                event = await asyncio.wait_for(ctx.event_bus.get(), timeout=0.05)
                await merged_queue.put(("event_bus", event))
            except TimeoutError:
                # Check if we should stop (will be cancelled when agent is done)
                continue
            except asyncio.CancelledError:
                # Drain remaining events before exiting
                while not ctx.event_bus.empty():
                    try:
                        event = ctx.event_bus.get_nowait()
                        await merged_queue.put(("event_bus", event))
                    except asyncio.QueueEmpty:
                        break
                raise

    async def run_agent():
        """Run agent and push events to merged queue."""
        nonlocal result, error
        try:
            async for item in agent.stream(user_message, max_iterations=max_iterations, history=history):
                if isinstance(item, str):
                    result = item
                elif isinstance(item, SSEEvent):
                    await merged_queue.put(("agent", item))
        except Exception as e:
            error = e
            await merged_queue.put((_ERROR, e))
        finally:
            await merged_queue.put((_DONE, None))

    # Start both tasks
    agent_task = asyncio.create_task(run_agent())
    forwarder_task = asyncio.create_task(forward_event_bus())

    try:
        # Consume merged events
        while True:
            if ctx.run.cancelled:
                yield _to_sse(CancelledEvent(run_id=ctx.run.run_id))
                return

            try:
                source, item = await asyncio.wait_for(merged_queue.get(), timeout=0.1)
            except TimeoutError:
                # Check if agent is done
                if agent_task.done():
                    # Drain any remaining events
                    while not merged_queue.empty():
                        source, item = merged_queue.get_nowait()
                        if source == _DONE:
                            break
                        if source == _ERROR:
                            raise item
                        if isinstance(item, SSEEvent):
                            yield _to_sse(item)
                    break
                continue

            if source == _DONE:
                # Agent finished, drain remaining and exit
                while not merged_queue.empty():
                    _src, evt = merged_queue.get_nowait()
                    if isinstance(evt, SSEEvent):
                        yield _to_sse(evt)
                break

            if source == _ERROR:
                raise item

            if isinstance(item, SSEEvent):
                yield _to_sse(item)

    finally:
        # Cancel forwarder and wait for cleanup
        forwarder_task.cancel()
        try:
            await forwarder_task
        except asyncio.CancelledError:
            pass

        # Drain any events forwarder put on merged_queue during cancellation
        while not merged_queue.empty():
            try:
                _src, evt = merged_queue.get_nowait()
                if isinstance(evt, SSEEvent):
                    yield _to_sse(evt)
            except asyncio.QueueEmpty:
                break

        if not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass

    if error:
        raise error

    yield {"_result": result}


@app.post("/tools/result")
async def submit_tool_result(request: ToolResultRequest):
    registry = get_run_registry()
    run = registry.get_run(request.run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.event_queue:
        await run.event_queue.put(
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
async def cancel_run(request: CancelRequest):
    registry = get_run_registry()
    registry.cancel_run(request.run_id)
    return {"status": "cancelled"}
