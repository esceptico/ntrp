"""YAML frontmatter on memory artifact files."""

from pathlib import Path

from ntrp.memory.artifacts import ArtifactMemoryStore
from ntrp.memory.frontmatter import (
    QuotedStr,
    dump_frontmatter,
    parse_frontmatter,
    strip_frontmatter,
)


def test_round_trip_preserves_dict():
    meta = {
        "kind": "fact",
        "title": "Example",
        "scope": {"kind": "global", "key": None},
        "labels": ["alpha", "beta"],
        "source": "consolidate",
        "record_count": 3,
        "generated": False,
        "editable": True,
        "updated": "2026-06-16T17:12:18+00:00",
    }
    parsed, body = parse_frontmatter(dump_frontmatter(meta) + "body\n")
    assert parsed == meta
    assert body == "body\n"


def test_updated_stays_string_after_round_trip():
    meta = {"updated": QuotedStr("2026-06-16T17:12:18.5+00:00")}
    parsed, _ = parse_frontmatter(dump_frontmatter(meta))
    assert isinstance(parsed["updated"], str)
    assert parsed["updated"] == "2026-06-16T17:12:18.5+00:00"


def test_strip_leaves_non_empty_body():
    content = dump_frontmatter({"kind": "fact"}) + "# Title\n\nbody text\n"
    body = strip_frontmatter(content)
    assert body.strip()
    assert not body.startswith("---")


def test_no_frontmatter_parses_via_convention():
    content = "# Plain doc\n\n- a bullet\n"
    parsed, body = parse_frontmatter(content)
    assert parsed == {}
    assert body == content


class EmptyRecords:
    async def list(self, *, limit):
        return []

    async def labels_for(self, record_ids):
        return {rid: [] for rid in record_ids}

    async def list_labels(self):
        return []


async def test_read_artifact_strips_frontmatter(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    store = ArtifactMemoryStore(root)
    await store.export_from_records(EmptyRecords())  # type: ignore[arg-type]

    readme = store.read_artifact("README.md")
    assert not readme.content.startswith("---")
    raw = (root / "README.md").read_text(encoding="utf-8")
    assert raw.startswith("---\n")


async def test_artifact_meta_reads_kind_and_scope_from_frontmatter(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "entities").mkdir()
    content = dump_frontmatter({
        "kind": "dossier",
        "title": "Regina",
        "scope": {"kind": "entity", "key": "regina"},
    }) + "# Regina\n\nbody\n"
    (root / "entities" / "regina.md").write_text(content, encoding="utf-8")

    store = ArtifactMemoryStore(root)
    artifact = store.read_artifact("entities/regina.md")
    assert artifact.kind == "dossier"
    assert artifact.scope_kind == "entity"
    assert artifact.scope_key == "regina"
    assert not artifact.content.startswith("---")
