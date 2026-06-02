"""LensFileStore edge cases surfaced by the bug hunt: YAML-safe frontmatter,
persisted timestamps, and graceful skip of a malformed scope (so one bad
hand-edited file never breaks listing of all lenses)."""

from pathlib import Path

from ntrp.memory.lens.file_store import LensFileStore
from ntrp.memory.models import (
    LensDetailLevel,
    LensProvenance,
    LensRenderMode,
    LensRow,
    LensStatus,
    Scope,
    ScopeKind,
)


def _lens(name: str, **kw) -> LensRow:
    return LensRow(
        id=kw.get("id", "l1"),
        name=name,
        criterion=kw.get("criterion", "## Belongs\nstuff"),
        scope=kw.get("scope", Scope(kind=ScopeKind.USER)),
        entity_type=kw.get("entity_type", "person"),
        detail_level=LensDetailLevel.STRUCTURED,
        render_mode=LensRenderMode.FLAT,
        provenance=LensProvenance.USER_AUTHORED,
        status=LensStatus.ACTIVE,
        page=None,
        created_at=kw.get("created_at", "2025-01-01T00:00:00+00:00"),
        updated_at=kw.get("updated_at", "2025-01-02T00:00:00+00:00"),
    )


def test_name_with_colon_round_trips(tmp_path: Path):
    # A title with ": " is the YAML mapping indicator — string-concat frontmatter
    # produced an unparseable file that vanished on read.
    store = LensFileStore(tmp_path)
    store.write(_lens("Project X: Q3 goals", id="px"))
    got = store.read("px")
    assert got is not None
    assert got.name == "Project X: Q3 goals"


def test_timestamps_persist_across_rewrite(tmp_path: Path):
    store = LensFileStore(tmp_path)
    store.write(_lens("People", id="people", created_at="2025-01-01T00:00:00+00:00"))
    # Re-read, edit the body, rewrite — created_at must NOT jump to the edit time.
    first = store.read("people")
    assert first.created_at == "2025-01-01T00:00:00+00:00"
    store.write(_lens("People", id="people", created_at=first.created_at, updated_at="2025-06-01T00:00:00+00:00"))
    again = store.read("people")
    assert again.created_at == "2025-01-01T00:00:00+00:00"
    assert again.updated_at == "2025-06-01T00:00:00+00:00"


def test_malformed_scope_is_skipped_not_crashing(tmp_path: Path):
    # A PROJECT lens hand-edited to drop scope_key must be skipped, not crash list().
    (tmp_path / "good.md").write_text(
        "---\ndirectory: Good\nentity_type: person\n---\n## Belongs\nx\n", encoding="utf-8"
    )
    (tmp_path / "bad.md").write_text(
        "---\ndirectory: Bad\nentity_type: person\nscope: project\n---\n## Belongs\nx\n",
        encoding="utf-8",
    )
    store = LensFileStore(tmp_path)
    lenses = store.list()  # must not raise
    slugs = {le.id for le in lenses}
    assert "good" in slugs
    assert "bad" not in slugs  # skipped gracefully
