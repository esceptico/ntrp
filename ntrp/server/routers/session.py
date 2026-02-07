from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ntrp.config import load_user_settings, save_user_settings
from ntrp.constants import EMBEDDING_MODELS, SUPPORTED_MODELS
from ntrp.context.compression import compress_context_async, count_tokens, find_compressible_range
from ntrp.logging import get_logger
from ntrp.server.runtime import get_runtime

logger = get_logger(__name__)

router = APIRouter(tags=["session"])


class SessionResponse(BaseModel):
    session_id: str
    sources: list[str]
    source_errors: dict[str, str]


class SourceToggles(BaseModel):
    gmail: bool | None = None
    calendar: bool | None = None
    memory: bool | None = None


class UpdateConfigRequest(BaseModel):
    chat_model: str | None = None
    memory_model: str | None = None
    max_depth: int | None = None
    vault_path: str | None = None
    browser: str | None = None
    browser_days: int | None = None
    sources: SourceToggles | None = None


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

    gmail_accounts: list[str] = []
    if runtime.gmail:
        try:
            gmail_accounts = runtime.gmail.list_accounts()
        except Exception:
            pass

    return {
        "chat_model": runtime.config.chat_model,
        "memory_model": runtime.config.memory_model,
        "embedding_model": runtime.config.embedding_model,
        "vault_path": runtime.config.vault_path,
        "browser": runtime.config.browser,
        "gmail_enabled": runtime.config.gmail,
        "gmail_accounts": gmail_accounts,
        "has_browser": runtime.config.browser is not None,
        "has_gmail": runtime.gmail is not None,
        "has_notes": runtime.config.vault_path is not None and runtime._sources.get("notes") is not None,
        "max_depth": runtime.max_depth,
        "memory_enabled": runtime.memory is not None,
        "sources": {
            "gmail": {"enabled": runtime.config.gmail, "connected": runtime.gmail is not None, "accounts": gmail_accounts},
            "calendar": {"enabled": runtime.config.calendar, "connected": "calendar" in runtime._sources},
            "memory": {"enabled": runtime.config.memory, "connected": runtime.memory is not None},
            "web": {"connected": "web" in runtime._sources},
            "notes": {"connected": "notes" in runtime._sources, "path": str(runtime.config.vault_path) if runtime.config.vault_path else None},
            "browser": {"connected": "browser" in runtime._sources, "type": runtime.config.browser},
        },
    }


@router.get("/models")
async def list_models():
    runtime = get_runtime()
    return {
        "models": list(SUPPORTED_MODELS.keys()),
        "chat_model": runtime.config.chat_model,
        "memory_model": runtime.config.memory_model,
    }


@router.patch("/config")
async def update_config(req: UpdateConfigRequest):
    runtime = get_runtime()

    async with runtime._config_lock:
        settings = load_user_settings()

        if req.chat_model:
            runtime.config.chat_model = req.chat_model
            settings["chat_model"] = req.chat_model
        if req.memory_model:
            runtime.config.memory_model = req.memory_model
            settings["memory_model"] = req.memory_model
        if req.chat_model or req.memory_model:
            save_user_settings(settings)

        if req.max_depth is not None:
            runtime.max_depth = req.max_depth

        if req.vault_path is not None:
            if req.vault_path == "":
                runtime.config.vault_path = None
                await runtime.reinit_notes(None)
                settings.pop("vault_path", None)
            else:
                vault_path = Path(req.vault_path).expanduser()
                if not vault_path.exists():
                    raise HTTPException(status_code=400, detail=f"Vault path does not exist: {vault_path}")
                runtime.config.vault_path = vault_path
                await runtime.reinit_notes(vault_path)
                settings["vault_path"] = str(vault_path)
            save_user_settings(settings)

        if req.browser is not None or req.browser_days is not None:
            browser = req.browser if req.browser is not None else runtime.config.browser
            browser_days = req.browser_days if req.browser_days is not None else runtime.config.browser_days

            if browser == "" or browser == "none":
                browser = None

            runtime.config.browser = browser
            runtime.config.browser_days = browser_days
            await runtime.reinit_browser(browser, browser_days)

            if browser:
                settings["browser"] = browser
            else:
                settings.pop("browser", None)
            settings["browser_days"] = browser_days
            save_user_settings(settings)

        if req.sources:
            sources_settings = settings.setdefault("sources", {})

            if req.sources.gmail is not None:
                runtime.config.gmail = req.sources.gmail
                sources_settings["gmail"] = req.sources.gmail
                if req.sources.gmail:
                    await runtime.reinit_gmail()
                else:
                    runtime._sources.pop("email", None)
                    runtime._source_errors.pop("email", None)
                    runtime.gmail = None

            if req.sources.calendar is not None:
                runtime.config.calendar = req.sources.calendar
                sources_settings["calendar"] = req.sources.calendar
                if req.sources.calendar:
                    await runtime.reinit_calendar()
                else:
                    runtime._sources.pop("calendar", None)
                    runtime._source_errors.pop("calendar", None)

            if req.sources.memory is not None:
                runtime.config.memory = req.sources.memory
                sources_settings["memory"] = req.sources.memory
                await runtime.reinit_memory(req.sources.memory)

            save_user_settings(settings)

    return {
        "chat_model": runtime.config.chat_model,
        "memory_model": runtime.config.memory_model,
        "max_depth": runtime.max_depth,
        "vault_path": str(runtime.config.vault_path) if runtime.config.vault_path else None,
        "browser": runtime.config.browser,
        "has_notes": runtime.config.vault_path is not None and runtime._sources.get("notes") is not None,
        "has_browser": runtime.config.browser is not None,
    }


class UpdateEmbeddingRequest(BaseModel):
    embedding_model: str


@router.get("/models/embedding")
async def list_embedding_models():
    runtime = get_runtime()
    return {
        "models": list(EMBEDDING_MODELS.keys()),
        "current": runtime.config.embedding_model,
    }


@router.post("/config/embedding")
async def update_embedding_model(req: UpdateEmbeddingRequest):
    runtime = get_runtime()

    if req.embedding_model not in EMBEDDING_MODELS:
        return {"status": "error", "message": f"Unknown model: {req.embedding_model}"}

    if req.embedding_model == runtime.config.embedding_model:
        return {"status": "unchanged", "embedding_model": req.embedding_model}

    # Update config
    new_dim = EMBEDDING_MODELS[req.embedding_model]
    runtime.config.embedding_model = req.embedding_model
    runtime.config.embedding_dim = new_dim

    # Persist to user settings
    settings = load_user_settings()
    settings["embedding_model"] = req.embedding_model
    settings["embedding_dim"] = new_dim
    save_user_settings(settings)

    # Clear search index and re-index
    await runtime.indexer.index.clear()
    runtime.start_indexing()

    # Memory vectors are now stale — they were embedded with the old model
    warning = None
    if runtime.memory:
        logger.warning(
            "Embedding model changed to %s — memory vectors are stale. Run /init or clear memory to re-embed.",
            req.embedding_model,
        )
        warning = "Memory vectors are stale and may return poor results. Clear memory or re-add facts to re-embed."

    return {
        "status": "reindexing",
        "embedding_model": req.embedding_model,
        "embedding_dim": new_dim,
        "warning": warning,
    }


@router.get("/context")
async def get_context_usage():
    import json

    from ntrp.core.prompts import build_system_prompt

    runtime = get_runtime()
    model = runtime.config.chat_model
    model_limit = SUPPORTED_MODELS.get(model, {}).get("tokens", 128000)

    # Get session messages
    data = await runtime.restore_session()
    messages = data.messages if data else []

    # Build current system prompt
    system_prompt = build_system_prompt(
        source_details=runtime.get_source_details(),
    )

    # Get tool schemas
    tools = runtime.tools or []
    tools_json = json.dumps(tools)

    # Count tokens (approximate: chars / 4)
    system_tokens = len(system_prompt) // 4
    tools_tokens = len(tools_json) // 4
    messages_tokens = count_tokens(messages) if messages else 0

    total = system_tokens + tools_tokens + messages_tokens

    return {
        "model": model,
        "limit": model_limit,
        "total": total,
        "system_prompt": system_tokens,
        "tools": tools_tokens,
        "messages": messages_tokens,
        "message_count": len(messages),
        "tool_count": len(tools),
    }


@router.post("/compact")
async def compact_context():
    runtime = get_runtime()
    model = runtime.config.chat_model

    # Try to restore most recent session
    data = await runtime.restore_session()
    if not data:
        return {
            "status": "no_session",
            "message": "No active session to compact",
        }

    session_state = data.state
    messages = data.messages

    before_tokens = count_tokens(messages)
    before_count = len(messages)

    # Check if there's anything to compress
    start, end = find_compressible_range(messages)
    if start == 0 and end == 0:
        return {
            "status": "nothing_to_compact",
            "message": f"Nothing to compact ({before_tokens:,} tokens, {before_count} messages)",
            "tokens": before_tokens,
            "message_count": before_count,
        }

    # Run compression (force=True for manual compaction)
    msg_count = end - start
    new_messages, was_compressed = await compress_context_async(
        messages=messages,
        model=model,
        force=True,
    )

    if was_compressed:
        # Save compacted session
        await runtime.save_session(session_state, new_messages)

        after_tokens = count_tokens(new_messages)
        saved = before_tokens - after_tokens

        return {
            "status": "compacted",
            "message": f"Compacted: {before_tokens:,} → {after_tokens:,} tokens (saved {saved:,})",
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "saved_tokens": saved,
            "messages_compressed": msg_count,
        }

    return {
        "status": "already_optimal",
        "message": f"Context already optimal ({before_tokens:,} tokens)",
        "tokens": before_tokens,
    }
