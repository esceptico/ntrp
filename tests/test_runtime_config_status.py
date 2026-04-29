import pytest

from ntrp.config import Config
from ntrp.server.runtime.core import Runtime


class _Integrations:
    def __init__(self):
        self.synced = []

    def sync(self, config):
        self.synced.append(config)


class _Knowledge:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.reloaded = []

    async def reload_config(self, config, stores, integrations):
        self.reloaded.append((config, stores, integrations))
        if self.fail:
            raise RuntimeError("knowledge reload failed")


async def _noop_reset():
    return None


async def _noop_sync_mcp(_config=None):
    return None


@pytest.mark.asyncio
async def test_runtime_reload_advances_config_version_after_success(monkeypatch):
    import ntrp.server.runtime.core as runtime_module

    original = Config(memory=False)
    runtime = Runtime(config=original)
    integrations = _Integrations()
    knowledge = _Knowledge()
    updated = Config(memory=False, max_depth=12)

    runtime.integrations = integrations
    runtime.knowledge = knowledge
    runtime.sync_mcp = _noop_sync_mcp

    monkeypatch.setattr(runtime_module, "get_config", lambda: updated)
    monkeypatch.setattr(runtime_module, "llm_reset", _noop_reset)
    monkeypatch.setattr(runtime_module, "llm_init", lambda _config: None)

    before = runtime.config_status()["config_version"]

    await runtime.reload_config()

    assert runtime.config is updated
    assert integrations.synced == [updated]
    assert knowledge.reloaded == [(updated, None, integrations)]
    assert runtime.config_status()["config_version"] == before + 1


@pytest.mark.asyncio
async def test_runtime_reload_does_not_advance_config_version_after_failure(monkeypatch):
    import ntrp.server.runtime.core as runtime_module

    original = Config(memory=False)
    runtime = Runtime(config=original)
    runtime.integrations = _Integrations()
    runtime.knowledge = _Knowledge(fail=True)
    runtime.sync_mcp = _noop_sync_mcp

    monkeypatch.setattr(runtime_module, "get_config", lambda: Config(memory=False, max_depth=12))
    monkeypatch.setattr(runtime_module, "llm_reset", _noop_reset)
    monkeypatch.setattr(runtime_module, "llm_init", lambda _config: None)

    before = runtime.config_status()["config_version"]

    with pytest.raises(RuntimeError, match="knowledge reload failed"):
        await runtime.reload_config()

    assert runtime.config is original
    assert runtime.config_status()["config_version"] == before
