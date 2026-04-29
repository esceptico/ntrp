import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ntrp.config import PROVIDER_KEY_FIELDS
from ntrp.llm.models import Provider, get_embedding_models_by_provider, get_models_by_provider
from ntrp.server.deps import require_config_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import ConnectProviderRequest, ConnectServiceRequest
from ntrp.services.config import ConfigService
from ntrp.settings import mask_api_key

router = APIRouter(tags=["providers"])


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


@router.get("/tool-providers")
async def list_tool_providers(runtime: Runtime = Depends(get_runtime)):
    """Unified list of tool providers: native integrations plus MCP servers."""
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
