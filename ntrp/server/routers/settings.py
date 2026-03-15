import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ntrp.config import PROVIDER_KEY_FIELDS, SERVICE_KEY_FIELDS
from ntrp.settings import mask_api_key
from ntrp.settings import load_user_settings, save_user_settings
from ntrp.llm.claude_oauth import is_configured as oauth_configured
from ntrp.llm.claude_oauth import login as oauth_login
from ntrp.llm.models import (
    OAUTH_PREFIX,
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
from ntrp.services.session import compact_session
from ntrp.services.config import ConfigService
from ntrp.services.session import SessionService
from ntrp.tools.directives import load_directives, save_directives

router = APIRouter(tags=["settings"])


def _google_errors(rt: Runtime) -> dict[str, str]:
    errors = []
    for key in ("gmail", "calendar"):
        if key in rt.source_mgr.errors:
            errors.append(rt.source_mgr.errors[key])
    return {"error": "; ".join(errors)} if errors else {}


def _config_response(rt: Runtime) -> dict:
    config = rt.config
    has_google = rt.source_mgr.has_google_auth()
    memory_connected = rt.memory is not None
    web_source = rt.source_mgr.sources.get("web")
    web_provider = getattr(web_source, "provider", "unknown") if web_source else "none"

    return {
        "chat_model": config.chat_model,
        "explore_model": config.explore_model,
        "memory_model": config.memory_model,
        "embedding_model": config.embedding_model,
        "web_search": config.web_search,
        "web_search_provider": web_provider,
        "vault_path": config.vault_path,
        "browser": config.browser,
        "google_enabled": config.google,
        "has_browser": config.browser is not None,
        "has_notes": config.vault_path is not None and rt.source_mgr.sources.get("notes") is not None,
        "max_depth": config.max_depth,
        "compression_threshold": config.compression_threshold,
        "max_messages": config.max_messages,
        "compression_keep_ratio": config.compression_keep_ratio,
        "summary_max_tokens": config.summary_max_tokens,
        "consolidation_interval": config.consolidation_interval,
        "memory_enabled": memory_connected,
        "sources": {
            "google": {
                "enabled": config.google,
                "connected": has_google,
                **(_google_errors(rt) or {}),
            },
            "memory": {
                "enabled": config.memory,
                "connected": memory_connected,
                "dreams": config.dreams,
                **(
                    {"error": "Embedding model required — configure an OpenAI or Google embedding model"}
                    if config.memory and not memory_connected
                    else {}
                ),
            },
            "web": {
                "connected": web_source is not None,
                "mode": config.web_search,
                "provider": web_provider,
                **({"error": rt.source_mgr.errors["web"]} if "web" in rt.source_mgr.errors else {}),
            },
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

    # Add Claude Pro/Max group when OAuth is configured
    config = runtime.config
    if oauth_configured() and Provider.ANTHROPIC.value in groups:
        groups["claude_oauth"] = [f"{OAUTH_PREFIX}{mid}" for mid in groups[Provider.ANTHROPIC.value]]

    return {
        "models": list_models(),
        "groups": [{"provider": p, "models": ms} for p, ms in groups.items()],
        "chat_model": config.chat_model,
        "explore_model": config.explore_model,
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

    # Claude Pro/Max (OAuth) — always show so users can initiate the flow
    anthropic_models = get_models_by_provider(Provider.ANTHROPIC)
    providers.append(
        {
            "id": "claude_oauth",
            "name": "Claude Pro/Max",
            "connected": oauth_configured(),
            "key_hint": None,
            "from_env": False,
            "models": list(anthropic_models.keys()),
            "embedding_models": [],
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


@router.post("/providers/anthropic/oauth")
async def connect_anthropic_oauth(
    runtime: Runtime = Depends(get_runtime),
):
    try:
        await asyncio.to_thread(oauth_login)
        await runtime.reload_config()
        return {"status": "connected", "provider": "anthropic"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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


SERVICE_META = {
    "exa": {"name": "Exa (Web Search)", "env_var": "EXA_API_KEY"},
    "telegram": {"name": "Telegram", "env_var": "TELEGRAM_BOT_TOKEN"},
}


@router.get("/services")
async def get_services(runtime: Runtime = Depends(get_runtime)):
    config = runtime.config
    services = []
    for sid, meta in SERVICE_META.items():
        field = SERVICE_KEY_FIELDS[sid]
        key = getattr(config, field, None)
        from_env = bool(os.environ.get(meta["env_var"]))
        services.append(
            {
                "id": sid,
                "name": meta["name"],
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
    for key in ("chat_model", "explore_model", "memory_model"):
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
