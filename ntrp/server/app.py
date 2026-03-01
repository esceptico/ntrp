from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from ntrp.config import verify_api_key
from ntrp.server.routers.automation import router as automation_router
from ntrp.server.routers.data import router as data_router
from ntrp.server.routers.gmail import router as gmail_router
from ntrp.server.routers.session import router as session_router
from ntrp.server.routers.skills import router as skills_router
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import CancelRequest, ChatRequest, ToolResultRequest
from ntrp.services.chat import ChatService


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = Runtime()
    await runtime.connect()
    runtime.start_indexing()
    runtime.start_scheduler()
    runtime.start_monitor()
    runtime.start_consolidation()
    app.state.runtime = runtime
    yield
    await runtime.close()


app = FastAPI(
    title="ntrp",
    description="Personal entropy reduction system - API server",
    version="0.3.4",
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


@app.get("/health")
async def health(request: Request, runtime: Runtime = Depends(get_runtime)):
    result: dict = {"status": "ok" if runtime.connected else "unavailable", "version": app.version}
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


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, runtime: Runtime = Depends(get_runtime)) -> StreamingResponse:
    svc = ChatService(runtime)
    try:
        ctx = await svc.prepare(request.message, request.skip_approvals, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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
