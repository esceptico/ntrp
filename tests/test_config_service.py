from copy import deepcopy

import pytest

from ntrp.services.config import ConfigService


@pytest.mark.asyncio
async def test_config_service_rolls_back_nested_settings_and_reloads_runtime(monkeypatch):
    import ntrp.services.config as config_module

    persisted = {"provider_keys": {"openai": "old-key"}}
    reload_seen: list[dict] = []

    def load_settings() -> dict:
        return deepcopy(persisted)

    def save_settings(settings: dict) -> None:
        nonlocal persisted
        persisted = deepcopy(settings)

    async def reload_config() -> None:
        reload_seen.append(deepcopy(persisted))
        if len(reload_seen) == 1:
            raise RuntimeError("reload failed")

    monkeypatch.setattr(config_module, "load_user_settings", load_settings)
    monkeypatch.setattr(config_module, "save_user_settings", save_settings)

    service = ConfigService(on_config_change=reload_config)

    with pytest.raises(RuntimeError, match="reload failed"):
        await service.connect_provider("openai", "new-key")

    assert persisted == {"provider_keys": {"openai": "old-key"}}
    assert reload_seen == [
        {"provider_keys": {"openai": "new-key"}},
        {"provider_keys": {"openai": "old-key"}},
    ]
