import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ntrp.config import PROVIDER_KEY_FIELDS
from ntrp.llm.models import (
    Provider,
    add_custom_model,
    get_embedding_models_by_provider,
    get_model,
    get_models_by_provider,
    list_embedding_models,
    list_models,
    remove_custom_model,
)
from ntrp.llm.models import (
    get_embedding_models as get_embedding_models_fn,
)
from ntrp.llm.models import (
    get_models as get_models_fn,
)
from ntrp.server.deps import require_config_service, require_session_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    AddCustomModelRequest,
    CompactRequest,
    ConnectProviderRequest,
    ConnectServiceRequest,
    UpdateConfigRequest,
    UpdateDirectivesRequest,
    UpdateEmbeddingRequest,
)
from ntrp.services.config import ConfigService
from ntrp.services.session import SessionService, compact_session
from ntrp.settings import load_user_settings, mask_api_key, save_user_settings
from ntrp.tools.directives import load_directives, save_directives

router = APIRouter(tags=["settings"])


def _config_response(rt: Runtime) -> dict:
    config = rt.config
    memory_connected = rt.memory is not None
    web_client = rt.integrations.get_client("web")
    web_provider = getattr(web_client, "provider", "unknown") if web_client else "none"

    sources: dict[str, dict] = {}
    for integration in rt.integrations.integrations.values():
        if integration.build is None:
            continue  # notifier-only, not a "source"
        entry: dict = {"connected": integration.id in rt.integrations.clients}
        if integration.id in rt.integrations.errors:
            entry["error"] = rt.integrations.errors[integration.id]
        sources[integration.id] = entry

    # Integration-specific extras the UI needs
    sources.setdefault("web", {}).update({
        "mode": config.web_search,
        "provider": web_provider,
    })
    sources.setdefault("notes", {})["path"] = str(config.vault_path) if config.vault_path else None
    sources.setdefault("slack", {}).update({
        "has_user_token": bool(config.slack_user_token),
        "has_bot_token": bool(config.slack_bot_token),
    })

    # Non-integration sources (google umbrella, memory)
    sources["google"] = {
        "enabled": config.google,
        "connected": "gmail" in rt.integrations.clients or "calendar" in rt.integrations.clients,
        **({"error": "; ".join(e for e in (rt.integrations.errors.get("gmail"), rt.integrations.errors.get("calendar")) if e)} if (rt.integrations.errors.get("gmail") or rt.integrations.errors.get("calendar")) else {}),
    }
    sources["memory"] = {
        "enabled": config.memory,
        "connected": memory_connected,
        "dreams": config.dreams,
        **(
            {"error": "Embedding model required — configure an OpenAI or Google embedding model"}
            if config.memory and not memory_connected
            else {}
        ),
    }

    return {
        "chat_model": config.chat_model,
        "research_model": config.research_model,
        "memory_model": config.memory_model,
        "embedding_model": config.embedding_model,
        "web_search": config.web_search,
        "web_search_provider": web_provider,
        "vault_path": config.vault_path,
        "google_enabled": config.google,
        "has_notes": "notes" in rt.integrations.clients,
        "max_depth": config.max_depth,
        "compression_threshold": config.compression_threshold,
        "max_messages": config.max_messages,
        "compression_keep_ratio": config.compression_keep_ratio,
        "summary_max_tokens": config.summary_max_tokens,
        "consolidation_interval": config.consolidation_interval,
        "memory_enabled": memory_connected,
        "sources": sources,
    }


# --- Config ---


@router.get("/config")
async def get_config(runtime: Runtime = Depends(get_runtime)):
    return _config_response(runtime)


@router.get("/models")
async def get_models(runtime: Runtime = Depends(get_runtime)):
    all_models = get_models_fn()
    groups: dict[str, list[str]] = {}
    for mid, m in all_models.items():
        provider_key = m.provider.value
        groups.setdefault(provider_key, []).append(mid)

    config = runtime.config
    return {
        "models": list_models(),
        "groups": [{"provider": p, "models": ms} for p, ms in groups.items()],
        "chat_model": config.chat_model,
        "research_model": config.research_model,
        "memory_model": config.memory_model,
    }


@router.patch("/config")
async def update_config(
    req: UpdateConfigRequest,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    fields = req.model_dump(exclude_unset=True)
    if sources := fields.pop("sources", None):
        fields.update({k: v for k, v in sources.items() if v is not None})
    try:
        await cfg_svc.update(**fields)
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _config_response(runtime)


# --- Providers ---


PROVIDER_META = {
    "anthropic": {"name": "Anthropic", "env_var": "ANTHROPIC_API_KEY", "provider": Provider.ANTHROPIC},
    "openai": {"name": "OpenAI", "env_var": "OPENAI_API_KEY", "provider": Provider.OPENAI},
    "google": {"name": "Google", "env_var": "GEMINI_API_KEY", "provider": Provider.GOOGLE},
    "openrouter": {"name": "OpenRouter", "env_var": "OPENROUTER_API_KEY", "provider": Provider.OPENROUTER},
}


@router.get("/providers")
async def get_providers(runtime: Runtime = Depends(get_runtime)):
    config = runtime.config
    providers = []

    for pid, meta in PROVIDER_META.items():
        field = PROVIDER_KEY_FIELDS[pid]
        key = getattr(config, field, None)
        from_env = bool(os.environ.get(meta["env_var"]))

        models = get_models_by_provider(meta["provider"])
        embedding_models = get_embedding_models_by_provider(meta["provider"])

        providers.append(
            {
                "id": pid,
                "name": meta["name"],
                "connected": bool(key),
                "key_hint": mask_api_key(key),
                "from_env": from_env,
                "models": list(models.keys()),
                "embedding_models": list(embedding_models.keys()),
            }
        )

    # Custom models entry
    custom_models = get_models_by_provider(Provider.CUSTOM)
    providers.append(
        {
            "id": "custom",
            "name": "Custom (OpenAI-compatible)",
            "connected": bool(custom_models),
            "key_hint": None,
            "from_env": False,
            "model_count": len(custom_models),
            "models": [
                {"id": mid, "base_url": m.base_url, "context_window": m.max_context_tokens}
                for mid, m in custom_models.items()
            ],
            "embedding_models": list(get_embedding_models_by_provider(Provider.CUSTOM).keys()),
        }
    )

    return {"providers": providers}


@router.post("/providers/{provider_id}/connect")
async def connect_provider(
    provider_id: str,
    req: ConnectProviderRequest,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    try:
        await cfg_svc.connect_provider(provider_id, req.api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.chat_model:
        try:
            await cfg_svc.update(chat_model=req.chat_model)
        except (ValueError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"status": "connected", "provider": provider_id}


@router.delete("/providers/{provider_id}")
async def disconnect_provider(
    provider_id: str,
    cfg_svc: ConfigService = Depends(require_config_service),
):
    try:
        await cfg_svc.disconnect_provider(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "disconnected", "provider": provider_id}


# --- Services ---


@router.get("/services")
async def get_services(runtime: Runtime = Depends(get_runtime)):
    config = runtime.config
    services = []
    for integration in runtime.integrations.integrations.values():
        for f in integration.service_fields:
            key = getattr(config, f.key, None)
            from_env = bool(f.env_var and os.environ.get(f.env_var))
            services.append(
                {
                    "id": f.key,
                    "name": f.label,
                    "connected": bool(key),
                    "key_hint": mask_api_key(key),
                    "from_env": from_env,
                }
            )
    return {"services": services}


@router.post("/services/{service_id}/connect")
async def connect_service(
    service_id: str,
    req: ConnectServiceRequest,
    cfg_svc: ConfigService = Depends(require_config_service),
):
    try:
        await cfg_svc.connect_service(service_id, req.api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "connected", "service": service_id}


@router.get("/providers")
async def list_providers(runtime: Runtime = Depends(get_runtime)):
    """Unified list of tool providers — native integrations + MCP servers."""
    native = runtime.integrations.list_providers()
    mcp = runtime.mcp_manager.list_providers() if runtime.mcp_manager else []
    return {
        "providers": [
            {
                "id": p.id,
                "label": p.label,
                "kind": p.kind,
                "status": p.health.status,
                "detail": p.health.detail,
                "tool_count": p.tool_count,
            }
            for p in [*native, *mcp]
        ]
    }


@router.post("/reload")
async def reload_runtime(runtime: Runtime = Depends(get_runtime)):
    """Re-read config from disk and rebuild sources, memory, MCP, etc.

    Use after editing .env or settings.json directly outside the UI.
    """
    await runtime.reload_config()
    return {"status": "reloaded"}


@router.delete("/services/{service_id}")
async def disconnect_service(
    service_id: str,
    cfg_svc: ConfigService = Depends(require_config_service),
):
    try:
        await cfg_svc.disconnect_service(service_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "disconnected", "service": service_id}


# --- Custom models ---


@router.post("/models/custom")
async def create_custom_model(
    req: AddCustomModelRequest,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    try:
        model = add_custom_model(
            model_id=req.model_id,
            base_url=req.base_url,
            context_window=req.context_window,
            max_output_tokens=req.max_output_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Store API key in settings.json if provided
    if req.api_key:
        settings = load_user_settings()
        custom_keys = settings.setdefault("custom_model_keys", {})
        custom_keys[req.model_id] = req.api_key
        save_user_settings(settings)

    # Reinit router to pick up new key
    await runtime.reload_config()

    return {"status": "created", "model_id": model.id}


@router.delete("/models/custom/{model_id:path}")
async def delete_custom_model(
    model_id: str,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    # Check if active model is being removed
    config = runtime.config
    clear_fields = {}
    for key in ("chat_model", "research_model", "memory_model"):
        if getattr(config, key) == model_id:
            clear_fields[key] = None

    try:
        remove_custom_model(model_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Remove stored API key
    settings = load_user_settings()
    custom_keys = settings.get("custom_model_keys", {})
    if model_id in custom_keys:
        del custom_keys[model_id]
        if not custom_keys:
            settings.pop("custom_model_keys", None)
        save_user_settings(settings)

    if clear_fields:
        await cfg_svc.update(**clear_fields)
    else:
        await runtime.reload_config()

    return {"status": "deleted", "model_id": model_id}


# --- Embedding ---


@router.get("/models/embedding")
async def get_embedding_models(runtime: Runtime = Depends(get_runtime)):
    all_models = get_embedding_models_fn()
    groups: dict[str, list[str]] = {}
    for mid, m in all_models.items():
        groups.setdefault(m.provider.value, []).append(mid)
    return {
        "models": list_embedding_models(),
        "groups": [{"provider": p, "models": ms} for p, ms in groups.items()],
        "current": runtime.config.embedding_model,
    }


@router.post("/config/embedding")
async def update_embedding_model(
    req: UpdateEmbeddingRequest,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    old_model = runtime.config.embedding_model

    try:
        await cfg_svc.update(embedding_model=req.embedding_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if runtime.config.embedding_model == old_model:
        return {"status": "unchanged", "embedding_model": old_model}

    return {
        "status": "reindexing",
        "embedding_model": req.embedding_model,
        "embedding_dim": runtime.config.embedding.dim if runtime.config.embedding else None,
    }


# --- Context ---


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
    messages = data.messages if data else []
    last_input_tokens = data.last_input_tokens if data else None

    return {
        "model": model,
        "limit": model_limit,
        "total": last_input_tokens,
        "message_count": len(messages),
        "tool_count": len(runtime.executor.get_tools()) if runtime.executor else 0,
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


# --- Directives ---


@router.get("/directives")
async def get_directives():
    return {"content": load_directives() or ""}


@router.put("/directives")
async def update_directives(req: UpdateDirectivesRequest):
    save_directives(req.content)
    return {"content": req.content.strip()}
