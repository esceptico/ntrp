import pytest

from ntrp.config import Config
from ntrp.llm.models import EmbeddingModel, Provider
from ntrp.server.runtime.core import Runtime
from ntrp.server.runtime.knowledge import KnowledgeRuntime


class _Integrations:
    def __init__(self):
        self.synced = []

    def sync(self, config):
        self.synced.append(config)


class _Knowledge:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.reloaded = []

    async def reload_config(self, config, stores):
        self.reloaded.append((config, stores))
        if self.fail:
            raise RuntimeError("knowledge reload failed")


async def _noop_reset():
    return None


async def _noop_sync_mcp(_config=None):
    return None


@pytest.mark.asyncio
async def test_runtime_reload_advances_config_version_after_success(monkeypatch):
    import ntrp.server.runtime.config as config_module

    original = Config(memory=False)
    runtime = Runtime(config=original)
    integrations = _Integrations()
    knowledge = _Knowledge()
    updated = Config(memory=False, max_depth=12)

    runtime.integrations = integrations
    runtime.knowledge = knowledge
    runtime.sync_mcp = _noop_sync_mcp

    monkeypatch.setattr(config_module, "get_config", lambda: updated)
    monkeypatch.setattr(config_module, "llm_reset", _noop_reset)
    monkeypatch.setattr(config_module, "llm_init", lambda _config: None)

    before = runtime.config_status()["config_version"]

    await runtime.reload_config()

    assert runtime.config is updated
    assert integrations.synced == [updated]
    assert knowledge.reloaded == [(updated, None)]
    assert runtime.config_status()["config_version"] == before + 1


@pytest.mark.asyncio
async def test_runtime_reload_does_not_advance_config_version_after_failure(monkeypatch):
    import ntrp.server.runtime.config as config_module

    original = Config(memory=False)
    runtime = Runtime(config=original)
    runtime.integrations = _Integrations()
    runtime.knowledge = _Knowledge(fail=True)
    runtime.sync_mcp = _noop_sync_mcp

    monkeypatch.setattr(config_module, "get_config", lambda: Config(memory=False, max_depth=12))
    monkeypatch.setattr(config_module, "llm_reset", _noop_reset)
    monkeypatch.setattr(config_module, "llm_init", lambda _config: None)

    before = runtime.config_status()["config_version"]

    with pytest.raises(RuntimeError, match="knowledge reload failed"):
        await runtime.reload_config()

    assert runtime.config is original
    assert runtime.config_status()["config_version"] == before


@pytest.mark.asyncio
async def test_knowledge_runtime_syncs_indexer_with_embedding_config(tmp_path, monkeypatch):
    import ntrp.llm.models as llm_models

    monkeypatch.setitem(llm_models._embedding_models, "test-embedding", EmbeddingModel("test-embedding", Provider.OPENAI, 3))

    initial = Config(ntrp_dir=tmp_path, memory=False, embedding_model=None)
    initial.db_dir.mkdir(parents=True, exist_ok=True)
    knowledge = KnowledgeRuntime(initial)

    assert knowledge.indexer is None
    assert knowledge.search_index is None

    enabled = Config(ntrp_dir=tmp_path, memory=False, embedding_model="test-embedding")
    await knowledge.reload_config(enabled, stores=None)

    assert knowledge.indexer is not None
    assert knowledge.search_index is not None

    disabled = Config(ntrp_dir=tmp_path, memory=False, embedding_model=None)
    await knowledge.reload_config(disabled, stores=None)

    assert knowledge.indexer is None
    assert knowledge.search_index is None
