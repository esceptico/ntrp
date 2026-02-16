from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ntrp.constants import HISTORY_MESSAGE_LIMIT
from ntrp.llm.models import EMBEDDING_DEFAULTS, get_model, list_models
from ntrp.server.runtime import get_runtime
from ntrp.server.schemas import (
    SessionResponse,
    UpdateConfigRequest,
    UpdateDirectivesRequest,
    UpdateEmbeddingRequest,
)
from ntrp.services.chat import ChatService

router = APIRouter(tags=["session"])


@router.get("/session/history")
async def get_session_history():
    runtime = get_runtime()
    data = await runtime.restore_session()
    if not data:
        return {"messages": []}

    history = []
    for msg in data.messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue

        content = msg.get("content", "")
        if not content or not isinstance(content, str) or not content.strip():
            continue

        history.append({"role": role, "content": content})

    return {"messages": history[-HISTORY_MESSAGE_LIMIT:]}


@router.get("/session")
async def get_session() -> SessionResponse:
    runtime = get_runtime()

    data = await runtime.restore_session()
    if data:
        session_state = data.state
    else:
        session_state = runtime.create_session()

    return SessionResponse(
        session_id=session_state.session_id,
        sources=runtime.get_available_sources(),
        source_errors=runtime.get_source_errors(),
    )


@router.post("/session/clear")
async def clear_session():
    runtime = get_runtime()

    if runtime.session_store:
        sessions = await runtime.session_store.list_sessions(limit=100)
        for s in sessions:
            await runtime.session_store.delete_session(s["session_id"])
    session_state = runtime.create_session()

    return {
        "status": "cleared",
        "session_id": session_state.session_id,
    }


@router.get("/config")
async def get_config():
    runtime = get_runtime()
    return runtime.config_service.get_summary(memory_connected=runtime.memory is not None)


@router.get("/models")
async def get_models():
    runtime = get_runtime()
    return {
        "models": list_models(),
        "chat_model": runtime.config.chat_model,
        "explore_model": runtime.config.explore_model,
        "memory_model": runtime.config.memory_model,
    }


@router.patch("/config")
async def update_config(req: UpdateConfigRequest):
    runtime = get_runtime()

    try:
        return await runtime.config_service.update(req)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/models/embedding")
async def list_embedding_models():
    runtime = get_runtime()
    return {
        "models": [m.id for m in EMBEDDING_DEFAULTS],
        "current": runtime.config.embedding_model,
    }


@router.post("/config/embedding")
async def update_embedding_model(req: UpdateEmbeddingRequest):
    runtime = get_runtime()
    return await runtime.config_service.update_embedding(req.embedding_model)


@router.get("/context")
async def get_context_usage():
    runtime = get_runtime()
    model = runtime.config.chat_model
    model_limit = get_model(model).context_window

    data = await runtime.restore_session()
    messages = data.messages if data else []
    last_input_tokens = data.last_input_tokens if data else None

    return {
        "model": model,
        "limit": model_limit,
        "total": last_input_tokens,
        "message_count": len(messages),
        "tool_count": len(runtime.tools or []),
    }


@router.post("/compact")
async def compact_context():
    svc = ChatService(get_runtime())
    return await svc.compact()


@router.get("/directives")
async def get_directives():
    runtime = get_runtime()
    return runtime.config_service.get_directives()


@router.put("/directives")
async def update_directives(req: UpdateDirectivesRequest):
    runtime = get_runtime()
    return runtime.config_service.update_directives(req.content)
