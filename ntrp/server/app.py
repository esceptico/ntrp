from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from ntrp.server.routers.dashboard import router as dashboard_router
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.schedule import router as schedule_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import get_run_registry, get_runtime, get_runtime_async, reset_runtime
from ntrp.server.schemas import CancelRequest, ChatRequest, ChoiceResultRequest, ToolResultRequest
from ntrp.services.chat import ChatService


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_runtime_async()
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
    return {"status": "ok" if runtime.connected else "unavailable"}


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
    return {"tools": runtime.executor.get_tool_metadata()}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    svc = ChatService(get_runtime())
    ctx = await svc.prepare(request.message, request.skip_approvals, session_id=request.session_id)
    return StreamingResponse(
        svc.stream(ctx),
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
