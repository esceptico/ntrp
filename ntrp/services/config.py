from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path

from ntrp.config import PERSIST_KEYS, PROVIDER_KEY_FIELDS
from ntrp.llm.models import Provider, get_models_by_provider
from ntrp.logging import get_logger
from ntrp.settings import load_user_settings, save_user_settings

_logger = get_logger(__name__)


class ConfigService:
    def __init__(self, on_config_change: Callable[[], Awaitable[None]]):
        self._on_config_change = on_config_change

    async def _with_rollback(self, mutate: Callable[[dict], None]) -> None:
        settings = load_user_settings()
        backup = deepcopy(settings)
        mutate(settings)
        save_user_settings(settings)
        try:
            await self._on_config_change()
        except Exception:
            save_user_settings(backup)
            try:
                await self._on_config_change()
            except Exception:
                _logger.exception("Failed to reload runtime after config rollback")
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

            for key in ("chat_model", "research_model", "memory_model"):
                if (val := settings.get(key)) and val in provider_models:
                    settings.pop(key)

        await self._with_rollback(mutate)

    def _valid_service_ids(self) -> set[str]:
        from ntrp.integrations import ALL_INTEGRATIONS

        return {f.key for i in ALL_INTEGRATIONS for f in i.service_fields}

    async def connect_service(self, service_id: str, api_key: str) -> None:
        valid = self._valid_service_ids()
        if service_id not in valid:
            raise ValueError(f"Unknown service: {service_id}. Available: {', '.join(sorted(valid))}")

        def mutate(settings: dict) -> None:
            settings.setdefault("service_keys", {})[service_id] = api_key

        await self._with_rollback(mutate)

    async def disconnect_service(self, service_id: str) -> None:
        valid = self._valid_service_ids()
        if service_id not in valid:
            raise ValueError(f"Unknown service: {service_id}. Available: {', '.join(sorted(valid))}")

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
