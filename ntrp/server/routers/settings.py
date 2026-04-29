from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ntrp.llm.models import (
    get_embedding_models as get_embedding_models_fn,
)
from ntrp.llm.models import (
    get_models as get_models_fn,
)
from ntrp.llm.models import list_embedding_models, list_models
from ntrp.server.deps import require_config_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    AddCustomModelRequest,
    UpdateConfigRequest,
    UpdateEmbeddingRequest,
)
from ntrp.services.config import ConfigService

router = APIRouter(tags=["settings"])


def _config_response(rt: Runtime) -> dict:
    config = rt.config
    memory_connected = rt.memory is not None
    web_client = rt.integrations.get_client("web")
    web_provider = getattr(web_client, "provider", "unknown") if web_client else "none"

    integrations: dict[str, dict] = {}
    for integration in rt.integrations.integrations.values():
        if integration.id.startswith("_") or integration.build is None:
            continue  # core builtins / notifier-only
        entry: dict = {"connected": integration.id in rt.integrations.clients}
        if integration.id in rt.integrations.errors:
            entry["error"] = rt.integrations.errors[integration.id]
        integrations[integration.id] = entry

    # Integration-specific extras the UI needs
    integrations.setdefault("web", {}).update(
        {
            "mode": config.web_search,
            "provider": web_provider,
        }
    )
    integrations.setdefault("notes", {})["path"] = str(config.vault_path) if config.vault_path else None
    integrations.setdefault("slack", {}).update(
        {
            "has_user_token": bool(config.slack_user_token),
            "has_bot_token": bool(config.slack_bot_token),
        }
    )

    # Umbrella + memory (not direct integrations)
    integrations["google"] = {
        "enabled": config.google,
        "connected": "gmail" in rt.integrations.clients or "calendar" in rt.integrations.clients,
        **(
            {
                "error": "; ".join(
                    e for e in (rt.integrations.errors.get("gmail"), rt.integrations.errors.get("calendar")) if e
                )
            }
            if (rt.integrations.errors.get("gmail") or rt.integrations.errors.get("calendar"))
            else {}
        ),
    }
    integrations["memory"] = {
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
        **rt.config_status(),
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
        "integrations": integrations,
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
    if toggles := fields.pop("integrations", None):
        fields.update({k: v for k, v in toggles.items() if v is not None})
    try:
        await cfg_svc.update(**fields)
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _config_response(runtime)


@router.post("/reload")
async def reload_runtime(runtime: Runtime = Depends(get_runtime)):
    """Re-read config from disk and rebuild integrations, memory, MCP, etc.

    Use after editing .env or settings.json directly outside the UI.
    """
    await runtime.reload_config()
    return {"status": "reloaded", **runtime.config_status()}


# --- Custom models ---


@router.post("/models/custom")
async def create_custom_model(
    req: AddCustomModelRequest,
    cfg_svc: ConfigService = Depends(require_config_service),
):
    try:
        model = await cfg_svc.create_custom_model(
            model_id=req.model_id,
            base_url=req.base_url,
            context_window=req.context_window,
            max_output_tokens=req.max_output_tokens,
            api_key=req.api_key,
        )
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "created", "model_id": model.id}


@router.delete("/models/custom/{model_id:path}")
async def delete_custom_model(
    model_id: str,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    config = runtime.config
    try:
        await cfg_svc.delete_custom_model(
            model_id,
            active_models={
                "chat_model": config.chat_model,
                "research_model": config.research_model,
                "memory_model": config.memory_model,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
