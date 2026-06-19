"""The nightly memory-maintenance builtin handler: consolidate the record pool,
then re-synthesize the prose surface (me.md / dossiers / active-work.md) so it
refreshes automatically instead of rotting between manual rebuilds."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import ntrp.memory.init as init_mod
from ntrp.server.runtime.automation import AutomationRuntime

pytestmark = pytest.mark.asyncio


class _Rep:
    def __init__(self, **kw):
        self.merged = kw.get("merged", 0)
        self.superseded = kw.get("superseded", 0)
        self.dropped = kw.get("dropped", 0)
        self.retyped = kw.get("retyped", 0)
        self.relabeled = kw.get("relabeled", 0)


def _runtime(consolidate, knowledge) -> AutomationRuntime:
    # Bypass the heavy __init__; the handler closure only reads these two getters.
    rt = object.__new__(AutomationRuntime)
    rt.get_consolidate = lambda: consolidate
    rt.get_knowledge = lambda: knowledge
    return rt


async def test_handler_consolidates_then_refreshes_prose():
    consolidate = AsyncMock()
    consolidate.run_once = AsyncMock(side_effect=[_Rep(merged=2, dropped=1), _Rep()])
    knowledge = AsyncMock()
    knowledge.rebuild_artifacts = AsyncMock(return_value=31)

    handler = _runtime(consolidate, knowledge)._build_memory_consolidate_handler()
    result = await handler(None)

    # Consolidation ran, THEN the prose surface was rebuilt over the fresh pool.
    knowledge.rebuild_artifacts.assert_awaited_once()
    assert "merged 2" in result and "dropped 1" in result
    assert "refreshed 31 artifacts" in result


async def test_handler_unavailable_without_memory_model():
    handler = _runtime(None, None)._build_memory_consolidate_handler()
    assert "unavailable" in await handler(None)


async def test_handler_survives_artifact_refresh_failure():
    consolidate = AsyncMock()
    consolidate.run_once = AsyncMock(side_effect=[_Rep(merged=1), _Rep()])
    knowledge = AsyncMock()
    knowledge.rebuild_artifacts = AsyncMock(side_effect=RuntimeError("boom"))

    handler = _runtime(consolidate, knowledge)._build_memory_consolidate_handler()
    result = await handler(None)

    # A synthesis failure must not lose the consolidation result or raise.
    assert "merged 1" in result
    assert "artifact refresh failed" in result


# --- integration_sync handler ------------------------------------------------


def _sync_runtime(knowledge, clients) -> AutomationRuntime:
    rt = object.__new__(AutomationRuntime)
    rt.get_knowledge = lambda: knowledge
    rt.get_integration_clients = lambda: clients
    return rt


async def test_sync_handler_runs_incremental_ingest(monkeypatch):
    captured = {}

    async def fake_ingest(knowledge, *, integration_clients, **kw):
        captured["clients"] = integration_clients
        return {"admitted": 3, "capped": False, "integrations": {"calendar": {"admitted": 2}, "gmail": {"admitted": 1}}}

    monkeypatch.setattr(init_mod, "run_integration_ingest", fake_ingest)
    knowledge = SimpleNamespace(memory_ready=True)
    handler = _sync_runtime(knowledge, {"calendar": object(), "gmail": object()})._build_integration_sync_handler()

    result = await handler(None)

    assert captured["clients"].keys() == {"calendar", "gmail"}
    assert "calendar: 2 new" in result and "gmail: 1 new" in result


async def test_sync_handler_skips_when_no_integrations():
    knowledge = SimpleNamespace(memory_ready=True)
    handler = _sync_runtime(knowledge, {})._build_integration_sync_handler()
    assert "skipped" in await handler(None)


async def test_sync_handler_unavailable_when_memory_not_ready():
    handler = _sync_runtime(SimpleNamespace(memory_ready=False), {"calendar": object()})._build_integration_sync_handler()
    assert "unavailable" in await handler(None)
