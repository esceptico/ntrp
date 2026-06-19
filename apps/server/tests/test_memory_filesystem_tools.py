"""Memory filesystem tools over the ArtifactMemoryStore projection."""

import os
import types
from pathlib import Path

import pytest

import ntrp.tools.memory as memory_tools
from ntrp.integrations.core import MEMORY
from ntrp.memory.records import RecordStore
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.memory import (
    MEMORY_RECORDS_SERVICE,
    MemoryPatchInput,
    MemoryReadInput,
    MemoryRebuildInput,
    MemorySearchInput,
    MemoryTreeInput,
    approve_memory_patch,
    memory_patch,
    memory_read,
    memory_rebuild,
    memory_search,
    memory_tree,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def store(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path / "memory.db", search_index=None)


@pytest.fixture
def artifacts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "memory"
    monkeypatch.setattr(
        memory_tools,
        "get_config",
        lambda: types.SimpleNamespace(
            memory_artifacts_dir=root, memory_db_path=tmp_path / "memory.db", memory_model=None
        ),
    )
    return root


def _execution(store=None):
    services = {MEMORY_RECORDS_SERVICE: store} if store is not None else {}
    return types.SimpleNamespace(
        ctx=types.SimpleNamespace(services=services, session_id="s1"),
        tool_id="t1",
        tool_name="memory",
    )


async def _export(store: RecordStore, artifacts_dir: Path):
    await store.add("the user prefers oolong tea", kind="fact")
    await store.add("remember to keep projection docs concise", kind="directive")
    artifacts = await memory_tools.ArtifactMemoryStore(artifacts_dir).export_from_records(store)
    assert artifacts
    return artifacts


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")


def _fifo_or_skip(path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs unavailable")
    try:
        os.mkfifo(path)
    except OSError as exc:
        pytest.skip(f"FIFOs unavailable: {exc}")


async def test_memory_filesystem_tools_registered_and_permission_gated():
    registry = ToolRegistry()
    for name, tool in MEMORY.tools.items():
        registry.register(name, tool, source="_memory")

    names_without = {s["function"]["name"] for s in registry.get_schemas(capabilities=frozenset())}
    names_with = {s["function"]["name"] for s in registry.get_schemas(capabilities=frozenset({MEMORY_RECORDS_SERVICE}))}

    expected = {"memory_tree", "memory_read", "memory_search", "memory_patch", "memory_rebuild"}
    assert expected.isdisjoint(names_without)
    assert expected.issubset(names_with)
    assert MEMORY.tools["memory_patch"].policy.requires_approval is True
    assert MEMORY.tools["memory_rebuild"].policy.requires_approval is True


async def test_memory_tree_read_and_search_use_artifact_store_safety(store: RecordStore, artifacts_dir: Path):
    await _export(store, artifacts_dir)
    execution = _execution(store)

    tree = await memory_tree(execution, MemoryTreeInput(depth=3))
    assert not tree.is_error
    assert "README.md" in tree.content
    assert tree.data["artifacts"]

    read = await memory_read(execution, MemoryReadInput(path="README.md", offset=1, limit=5))
    assert not read.is_error
    assert "memory" in read.content.lower()
    assert read.data["path"] == "README.md"

    search = await memory_search(execution, MemorySearchInput(query="projection", limit=10))
    assert not search.is_error
    assert search.data["matches"]


@pytest.mark.parametrize("bad_path", ["/tmp/README.md", "../README.md", ".secret/file.md", "README.txt"])
async def test_memory_read_search_patch_reject_bad_paths(store: RecordStore, artifacts_dir: Path, bad_path: str):
    await _export(store, artifacts_dir)
    execution = _execution(store)

    assert (await memory_read(execution, MemoryReadInput(path=bad_path))).is_error
    assert (await memory_search(execution, MemorySearchInput(query="x", path=bad_path))).is_error
    assert (await memory_patch(execution, MemoryPatchInput(path=bad_path, old_text="x", new_text="y", force_generated=True))).is_error


async def test_memory_tools_reject_symlink_and_fifo(store: RecordStore, artifacts_dir: Path):
    await _export(store, artifacts_dir)
    outside = artifacts_dir.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    readme = artifacts_dir / "README.md"
    readme.unlink()
    _symlink_or_skip(readme, outside)
    execution = _execution(store)

    assert (await memory_read(execution, MemoryReadInput(path="README.md"))).is_error
    assert (await memory_search(execution, MemorySearchInput(query="outside", path="README.md"))).is_error
    assert (await memory_patch(execution, MemoryPatchInput(path="README.md", old_text="outside", new_text="inside", force_generated=True))).is_error

    readme.unlink()
    _fifo_or_skip(readme)
    assert (await memory_read(execution, MemoryReadInput(path="README.md"))).is_error


async def test_memory_patch_refuses_generated_without_force_and_force_patch_audits(store: RecordStore, artifacts_dir: Path):
    await _export(store, artifacts_dir)
    execution = _execution(store)
    store_obj = memory_tools.ArtifactMemoryStore(artifacts_dir)
    old = store_obj.read_artifact("README.md").content.splitlines()[0]

    refused = await memory_patch(execution, MemoryPatchInput(path="README.md", old_text=old, new_text="# Patched memory", force_generated=False))
    assert refused.is_error
    assert "Refusing to edit generated" in refused.content

    approval = await approve_memory_patch(execution, MemoryPatchInput(path="README.md", old_text=old, new_text="# Patched memory", force_generated=True))
    assert approval is not None
    assert approval.description == "Force edit generated memory artifact README.md"
    assert "-" in (approval.diff or "") and "+" in (approval.diff or "")

    patched = await memory_patch(execution, MemoryPatchInput(path="README.md", old_text=old, new_text="# Patched memory", force_generated=True))
    assert not patched.is_error
    assert store_obj.read_artifact("README.md").content.startswith("# Patched memory")
    changelog = "\n".join(p.read_text(encoding="utf-8") for p in (artifacts_dir / "changelog").glob("**/*.md"))
    assert "memory filesystem patched" not in changelog  # maintenance edits aren't logged as changelog noise


async def test_memory_patch_requires_unique_old_text(store: RecordStore, artifacts_dir: Path):
    await _export(store, artifacts_dir)
    path = artifacts_dir / "README.md"
    path.write_text("# A\nrepeat\nrepeat\n", encoding="utf-8")

    result = await memory_patch(_execution(store), MemoryPatchInput(path="README.md", old_text="repeat", new_text="once", force_generated=True))

    assert result.is_error
    assert result.preview == "Ambiguous"


async def test_memory_rebuild_uses_record_store_and_returns_artifacts(store: RecordStore, artifacts_dir: Path):
    await store.add("the user likes rebuild tests", kind="fact")
    result = await memory_rebuild(_execution(store), MemoryRebuildInput(reason="test"))

    assert not result.is_error
    assert result.data["artifact_count"] > 0
    assert result.data["root"] == str(artifacts_dir)
    assert (artifacts_dir / "README.md").exists()
    assert any(path.endswith("index.md") for path in result.data["artifacts"])


async def test_memory_rebuild_requires_memory_records_service(artifacts_dir: Path):
    result = await memory_rebuild(_execution(None), MemoryRebuildInput())

    assert result.is_error
    assert result.preview == "Memory unavailable"
