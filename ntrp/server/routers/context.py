from fastapi import APIRouter, Depends, HTTPException

from ntrp.llm.models import get_model
from ntrp.server.deps import require_session_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import CompactRequest, UpdateDirectivesRequest
from ntrp.services.session import SessionService, compact_session
from ntrp.tools.deferred import is_deferred_tool, tool_schema_names, visible_tool_names
from ntrp.tools.directives import load_directives, save_directives

router = APIRouter(tags=["context"])


@router.get("/context")
async def get_context_usage(
    runtime: Runtime = Depends(get_runtime),
    svc: SessionService = Depends(require_session_service),
    session_id: str | None = None,
):
    model = runtime.config.chat_model
    if not model:
        raise HTTPException(status_code=503, detail="No chat model configured")
    model_limit = get_model(model).max_context_tokens

    data = await svc.load(session_id)
    resolved_session_id = data.state.session_id if data else session_id
    active_run = runtime.run_registry.get_active_run(resolved_session_id) if resolved_session_id else None
    messages = active_run.messages if active_run else (data.messages if data else [])
    last_input_tokens = data.last_input_tokens if data else None
    tools = runtime.executor.get_tools() if runtime.executor else []
    allowed_tool_names = tool_schema_names(tools)
    loaded_tools = active_run.loaded_tools if active_run else set()
    capabilities = frozenset(runtime.executor.tool_services) if runtime.executor else frozenset()
    visible_tools = (
        visible_tool_names(
            runtime.executor.registry,
            capabilities,
            loaded_tools,
            allowed_names=allowed_tool_names,
        )
        if runtime.executor
        else set()
    )
    deferred_tools = {
        name for name in allowed_tool_names if runtime.executor and is_deferred_tool(name, runtime.executor.registry)
    }
    loaded_deferred_tools = loaded_tools & deferred_tools

    return {
        "model": model,
        "limit": model_limit,
        "total": last_input_tokens,
        "message_count": len(messages),
        "tool_count": len(tools),
        "visible_tool_count": len(visible_tools),
        "deferred_tool_count": len(deferred_tools),
        "loaded_tool_count": len(loaded_deferred_tools),
    }


@router.post("/compact")
async def compact_context(runtime: Runtime = Depends(get_runtime), req: CompactRequest | None = None):
    session_id = req.session_id if req else None
    try:
        return await compact_session(
            runtime.session_service,
            model=runtime.config.chat_model,
            session_id=session_id,
            keep_ratio=runtime.config.compression_keep_ratio,
            summary_max_tokens=runtime.config.summary_max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/directives")
async def get_directives():
    return {"content": load_directives() or ""}


@router.put("/directives")
async def update_directives(req: UpdateDirectivesRequest):
    save_directives(req.content)
    return {"content": req.content.strip()}
