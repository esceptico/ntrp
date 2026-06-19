from pathlib import Path
from types import SimpleNamespace

import pytest

import ntrp.memory.artifacts as artifacts_mod
from ntrp.memory.records import RecordStore
from ntrp.server.runtime.knowledge import KnowledgeRuntime

pytestmark = pytest.mark.asyncio


class CountingArtifactStore:
    calls = 0

    def __init__(self, root: Path):
        self.root = root

    async def export_from_records(self, records, *, llm=None, model="", limit=None):
        type(self).calls += 1
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "README.md").write_text("# generated\n")
        return [SimpleNamespace(path="README.md")]


def _runtime(records: RecordStore, tmp_path: Path) -> KnowledgeRuntime:
    rt = object.__new__(KnowledgeRuntime)
    rt.config = SimpleNamespace(
        memory_db_path=tmp_path / "memory.db",
        memory_artifacts_dir=tmp_path / "artifacts",
        memory_model=None,
    )
    rt._record_store = records
    return rt


async def test_publish_artifacts_if_dirty_skips_unchanged_export(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(artifacts_mod, "ArtifactMemoryStore", CountingArtifactStore)
    CountingArtifactStore.calls = 0
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    await records.add("the user prefers terse updates", kind="fact")
    runtime = _runtime(records, tmp_path)

    first = await runtime.publish_artifacts_if_dirty()
    second = await runtime.publish_artifacts_if_dirty()

    assert first.refreshed is True
    assert first.artifact_count == 1
    assert second.refreshed is False
    assert second.artifact_count == 0
    assert CountingArtifactStore.calls == 1


async def test_publish_artifacts_if_dirty_refreshes_when_labels_change(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(artifacts_mod, "ArtifactMemoryStore", CountingArtifactStore)
    CountingArtifactStore.calls = 0
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    record = await records.add("memory labels affect dossiers", kind="fact")
    runtime = _runtime(records, tmp_path)

    await runtime.publish_artifacts_if_dirty()
    await records.set_labels(record.id, ["Memory"], entity_labels=["Task 3"])
    refreshed = await runtime.publish_artifacts_if_dirty()

    assert refreshed.refreshed is True
    assert refreshed.artifact_count == 1
    assert CountingArtifactStore.calls == 2


async def test_publish_artifacts_if_dirty_refreshes_when_records_change(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(artifacts_mod, "ArtifactMemoryStore", CountingArtifactStore)
    CountingArtifactStore.calls = 0
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    record = await records.add("old artifact text", kind="fact")
    runtime = _runtime(records, tmp_path)

    await runtime.publish_artifacts_if_dirty()
    await records.update(record.id, "new artifact text")
    refreshed = await runtime.publish_artifacts_if_dirty()

    assert refreshed.refreshed is True
    assert refreshed.artifact_count == 1
    assert CountingArtifactStore.calls == 2


async def test_publish_artifacts_if_dirty_refreshes_when_artifact_tree_drifts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(artifacts_mod, "ArtifactMemoryStore", CountingArtifactStore)
    CountingArtifactStore.calls = 0
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    await records.add("artifact files can drift", kind="fact")
    runtime = _runtime(records, tmp_path)

    await runtime.publish_artifacts_if_dirty()
    (tmp_path / "artifacts" / "README.md").unlink()
    refreshed = await runtime.publish_artifacts_if_dirty()

    assert refreshed.refreshed is True
    assert CountingArtifactStore.calls == 2


async def test_forced_rebuild_updates_dirty_checkpoint(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(artifacts_mod, "ArtifactMemoryStore", CountingArtifactStore)
    CountingArtifactStore.calls = 0
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    await records.add("manual rebuild should satisfy scheduled publish", kind="fact")
    runtime = _runtime(records, tmp_path)

    assert await runtime.rebuild_artifacts() == 1
    skipped = await runtime.publish_artifacts_if_dirty()

    assert skipped.refreshed is False
    assert CountingArtifactStore.calls == 1


async def test_artifact_fingerprint_includes_created_at(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    record = await records.add("created time affects artifact ordering", kind="fact")
    runtime = _runtime(records, tmp_path)
    before = await runtime._artifact_fingerprint()

    conn = await records._ensure_conn()
    await conn.execute("UPDATE records SET created_at = ? WHERE id = ?", ("2099-01-01T00:00:00+00:00", record.id))
    await conn.commit()

    assert await runtime._artifact_fingerprint() != before
