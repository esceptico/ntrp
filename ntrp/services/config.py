from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ntrp.config import PERSIST_KEYS, PROVIDER_KEY_FIELDS, SERVICE_KEY_FIELDS, load_user_settings, save_user_settings
from ntrp.llm.claude_oauth import clear as clear_oauth
from ntrp.llm.models import Provider, get_models_by_provider, is_oauth_model

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


class ConfigService:
    def __init__(self, runtime: "Runtime"):
        self.runtime = runtime

    async def _with_rollback(self, mutate: Callable[[dict], None]) -> None:
        settings = load_user_settings()
        backup = dict(settings)
        mutate(settings)
        save_user_settings(settings)
        try:
            await self.runtime.reload_config()
        except Exception:
            save_user_settings(backup)
            raise

    async def update(self, **fields) -> None:
        if "vault_path" in fields:
            path = fields["vault_path"]
            if path:
                vault = Path(path).expanduser()
                if not vault.exists():
                    raise ValueError(f"Vault path does not exist: {vault}")
                fields["vault_path"] = str(vault)
            else:
                fields["vault_path"] = None

        persist = {k: v for k, v in fields.items() if k in PERSIST_KEYS}
        if not persist:
            return

        def mutate(settings: dict) -> None:
            for key, value in persist.items():
                if value is None:
                    settings.pop(key, None)
                else:
                    settings[key] = value

        await self._with_rollback(mutate)

    async def connect_provider(self, provider: str, api_key: str) -> None:
        if provider not in PROVIDER_KEY_FIELDS:
            raise ValueError(f"Unknown provider: {provider}. Available: {', '.join(PROVIDER_KEY_FIELDS)}")

        def mutate(settings: dict) -> None:
            settings.setdefault("provider_keys", {})[provider] = api_key

        await self._with_rollback(mutate)

    async def disconnect_provider(self, provider: str) -> None:
        if provider == "claude_oauth":
            return await self._disconnect_oauth()

        if provider not in PROVIDER_KEY_FIELDS:
            raise ValueError(f"Unknown provider: {provider}. Available: {', '.join(PROVIDER_KEY_FIELDS)}")

        provider_models = get_models_by_provider(Provider(provider))

        def mutate(settings: dict) -> None:
            provider_keys = settings.get("provider_keys", {})
            provider_keys.pop(provider, None)
            if not provider_keys:
                settings.pop("provider_keys", None)
            else:
                settings["provider_keys"] = provider_keys

            for key in ("chat_model", "explore_model", "memory_model"):
                if settings.get(key) in provider_models:
                    settings.pop(key)

        await self._with_rollback(mutate)

    async def _disconnect_oauth(self) -> None:
        def mutate(settings: dict) -> None:
            for key in ("chat_model", "explore_model", "memory_model"):
                if is_oauth_model(settings.get(key, "")):
                    settings.pop(key)

        await self._with_rollback(mutate)
        clear_oauth()

    async def connect_service(self, service_id: str, api_key: str) -> None:
        if service_id not in SERVICE_KEY_FIELDS:
            raise ValueError(f"Unknown service: {service_id}. Available: {', '.join(SERVICE_KEY_FIELDS)}")

        def mutate(settings: dict) -> None:
            settings.setdefault("service_keys", {})[service_id] = api_key

        await self._with_rollback(mutate)

    async def disconnect_service(self, service_id: str) -> None:
        if service_id not in SERVICE_KEY_FIELDS:
            raise ValueError(f"Unknown service: {service_id}. Available: {', '.join(SERVICE_KEY_FIELDS)}")

        def mutate(settings: dict) -> None:
            service_keys = settings.get("service_keys", {})
            service_keys.pop(service_id, None)
            if not service_keys:
                settings.pop("service_keys", None)
            else:
                settings["service_keys"] = service_keys

        await self._with_rollback(mutate)

    async def add_mcp_server(self, name: str, config: dict) -> None:
        def mutate(settings: dict) -> None:
            settings.setdefault("mcp_servers", {})[name] = config

        await self._with_rollback(mutate)

    async def update_mcp_server(self, name: str, config: dict) -> None:
        settings = load_user_settings()
        if name not in settings.get("mcp_servers", {}):
            raise ValueError(f"MCP server {name!r} not found")

        def mutate(s: dict) -> None:
            s.get("mcp_servers", {})[name] = config

        await self._with_rollback(mutate)

    async def toggle_mcp_server(self, name: str, enabled: bool) -> None:
        settings = load_user_settings()
        if name not in settings.get("mcp_servers", {}):
            raise ValueError(f"MCP server {name!r} not found")

        def mutate(s: dict) -> None:
            if enabled:
                s.get("mcp_servers", {})[name].pop("enabled", None)
            else:
                s.get("mcp_servers", {})[name]["enabled"] = False

        await self._with_rollback(mutate)

    async def remove_mcp_server(self, name: str) -> None:
        def mutate(settings: dict) -> None:
            mcp_servers = settings.get("mcp_servers", {})
            mcp_servers.pop(name, None)
            if not mcp_servers:
                settings.pop("mcp_servers", None)
            else:
                settings["mcp_servers"] = mcp_servers

        await self._with_rollback(mutate)
