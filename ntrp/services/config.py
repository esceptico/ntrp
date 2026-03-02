from pathlib import Path
from typing import TYPE_CHECKING

from ntrp.config import PERSIST_KEYS, PROVIDER_KEY_FIELDS, load_user_settings, save_user_settings
from ntrp.llm.models import Provider, get_models_by_provider

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


class ConfigService:
    def __init__(self, runtime: "Runtime"):
        self.runtime = runtime

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

        settings = load_user_settings()
        backup = dict(settings)
        for key, value in persist.items():
            if value is None:
                settings.pop(key, None)
            else:
                settings[key] = value
        save_user_settings(settings)

        try:
            await self.runtime.reload_config()
        except Exception:
            save_user_settings(backup)
            raise

    async def connect_provider(self, provider: str, api_key: str) -> None:
        if provider not in PROVIDER_KEY_FIELDS:
            raise ValueError(f"Unknown provider: {provider}. Available: {', '.join(PROVIDER_KEY_FIELDS)}")

        settings = load_user_settings()
        backup = dict(settings)
        provider_keys = settings.setdefault("provider_keys", {})
        provider_keys[provider] = api_key
        save_user_settings(settings)

        try:
            await self.runtime.reload_config()
        except Exception:
            save_user_settings(backup)
            raise

    async def disconnect_provider(self, provider: str) -> None:
        if provider not in PROVIDER_KEY_FIELDS:
            raise ValueError(f"Unknown provider: {provider}. Available: {', '.join(PROVIDER_KEY_FIELDS)}")

        settings = load_user_settings()
        backup = dict(settings)
        provider_keys = settings.get("provider_keys", {})
        provider_keys.pop(provider, None)
        if not provider_keys:
            settings.pop("provider_keys", None)
        else:
            settings["provider_keys"] = provider_keys

        # Clear model selections that belong to this provider
        provider_enum = {"anthropic": Provider.ANTHROPIC, "openai": Provider.OPENAI, "google": Provider.GOOGLE}[provider]
        provider_models = get_models_by_provider(provider_enum)
        for key in ("chat_model", "explore_model", "memory_model"):
            if settings.get(key) in provider_models:
                settings.pop(key)

        save_user_settings(settings)

        try:
            await self.runtime.reload_config()
        except Exception:
            save_user_settings(backup)
            raise
