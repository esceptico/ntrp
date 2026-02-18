from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ntrp.constants import HISTORY_MESSAGE_LIMIT
from ntrp.llm.models import EMBEDDING_DEFAULTS, get_model, list_models
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    ClearSessionRequest,
    CompactRequest,
    CreateSessionRequest,
    RenameSessionRequest,
    SessionResponse,
    UpdateConfigRequest,
    UpdateDirectivesRequest,
    UpdateEmbeddingRequest,
)
from ntrp.services.chat import ChatService
from ntrp.tools.directives import load_directives, save_directives

router = APIRouter(tags=["session"])


def _config_response(rt: Runtime) -> dict:
    config = rt.config
    has_google = rt.source_mgr.has_google_auth()
    memory_connected = rt.memory is not None

    return {
        "chat_model": config.chat_model,
        "explore_model": config.explore_model,
        "memory_model": config.memory_model,
        "embedding_model": config.embedding_model,
        "vault_path": config.vault_path,
        "browser": config.browser,
        "gmail_enabled": config.gmail,
        "has_browser": config.browser is not None,
        "has_notes": config.vault_path is not None and rt.source_mgr.sources.get("notes") is not None,
        "max_depth": rt.max_depth,
        "memory_enabled": memory_connected,
        "sources": {
            "gmail": {"enabled": config.gmail, "connected": has_google},
            "calendar": {"enabled": config.calendar, "connected": has_google},
            "memory": {"enabled": config.memory, "connected": memory_connected},
            "web": {"connected": "web" in rt.source_mgr.sources},
            "notes": {
                "connected": "notes" in rt.source_mgr.sources,
                "path": str(config.vault_path) if config.vault_path else None,
            },
            "browser": {
                "connected": "browser" in rt.source_mgr.sources,
                "type": config.browser,
            },
        },
    }


# --- Session ---


@router.get("/session/history")
async def get_session_history(session_id: str | None = None):
    runtime = get_runtime()

    if session_id:
        data = await runtime.load_session(session_id)
    else:
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
async def get_session(session_id: str | None = None) -> SessionResponse:
    runtime = get_runtime()

    if session_id:
        data = await runtime.load_session(session_id)
    else:
        data = await runtime.restore_session()

    if data:
        session_state = data.state
    else:
        session_state = runtime.create_session()

    return SessionResponse(
        session_id=session_state.session_id,
        sources=runtime.get_available_sources(),
        source_errors=runtime.get_source_errors(),
        name=session_state.name,
    )


@router.post("/session/clear")
async def clear_session(req: ClearSessionRequest | None = None):
    runtime = get_runtime()
    target_id = req.session_id if req else None

    if target_id:
        data = await runtime.load_session(target_id)
    else:
        data = await runtime.restore_session()

    if not data:
        return {"status": "cleared", "session_id": None}

    data.state.last_activity = data.state.started_at
    await runtime.save_session(data.state, [])

    return {
        "status": "cleared",
        "session_id": data.state.session_id,
    }


# --- Multi-session ---


@router.post("/sessions")
async def create_session(req: CreateSessionRequest | None = None):
    runtime = get_runtime()
    name = req.name if req else None
    state = runtime.create_session(name=name)
    await runtime.save_session(state, [])
    return {
        "session_id": state.session_id,
        "name": state.name,
        "started_at": state.started_at.isoformat(),
        "last_activity": state.last_activity.isoformat(),
        "message_count": 0,
    }


@router.get("/sessions")
async def list_sessions():
    runtime = get_runtime()
    sessions = await runtime.session_store.list_sessions(limit=20)
    return {"sessions": sessions}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, req: RenameSessionRequest):
    runtime = get_runtime()
    updated = await runtime.session_store.update_session_name(session_id, req.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "name": req.name}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    runtime = get_runtime()
    deleted = await runtime.session_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


# --- Config ---


@router.get("/config")
async def get_config():
    return _config_response(get_runtime())


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
    fields = req.model_dump(exclude_unset=True)
    if sources := fields.pop("sources", None):
        fields.update({k: v for k, v in sources.items() if v is not None})
    try:
        await runtime.config_service.update(**fields)
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _config_response(runtime)


# --- Embedding ---


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
    old_model = runtime.config.embedding_model

    try:
        await runtime.config_service.update(embedding_model=req.embedding_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if runtime.config.embedding_model == old_model:
        return {"status": "unchanged", "embedding_model": old_model}

    return {
        "status": "reindexing",
        "embedding_model": req.embedding_model,
        "embedding_dim": runtime.config.embedding.dim,
    }


# --- Context ---


@router.get("/context")
async def get_context_usage(session_id: str | None = None):
    runtime = get_runtime()
    model = runtime.config.chat_model
    model_limit = get_model(model).max_context_tokens

    if session_id:
        data = await runtime.load_session(session_id)
    else:
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
async def compact_context(req: CompactRequest | None = None):
    session_id = req.session_id if req else None
    svc = ChatService(get_runtime())
    return await svc.compact(session_id=session_id)


# --- Directives ---


@router.get("/directives")
async def get_directives():
    return {"content": load_directives() or ""}


@router.put("/directives")
async def update_directives(req: UpdateDirectivesRequest):
    save_directives(req.content)
    return {"content": req.content.strip()}
