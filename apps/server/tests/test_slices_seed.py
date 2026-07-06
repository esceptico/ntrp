"""Test slices seed CLI."""

from pathlib import Path

import pytest

from ntrp.slices.registry import SliceRegistry
from ntrp.slices.seed import promote


@pytest.fixture
def tmp_registry_and_topics(tmp_path: Path) -> tuple[SliceRegistry, Path]:
    """Create a temporary registry file and topics dir."""
    registry_file = tmp_path / "slices.json"
    topics_dir = tmp_path / "topics"
    topics_dir.mkdir()

    registry = SliceRegistry(registry_file)
    return registry, topics_dir


def test_promote_adds_new_slices(tmp_registry_and_topics: tuple[SliceRegistry, Path]) -> None:
    """Test that promote adds new slices to an empty registry."""
    registry, topics_dir = tmp_registry_and_topics

    # Create fake topic pages
    (topics_dir / "o-1a.md").write_text("---\ntitle: O-1A Model\n---\nContent here.")
    (topics_dir / "dex.md").write_text("---\ntitle: Developer Experience\n---\nMore content.")

    # Promote both
    result = promote(registry, topics_dir, ["o-1a", "dex"])

    assert len(result) == 2
    assert result[0].key == "o-1a"
    assert result[0].title == "O-1A Model"
    assert result[0].page_path == "topics/o-1a.md"
    assert result[0].autonomy == "observe"

    assert result[1].key == "dex"
    assert result[1].title == "Developer Experience"
    assert result[1].page_path == "topics/dex.md"
    assert result[1].autonomy == "observe"

    # Verify they're persisted
    loaded = registry.load()
    assert len(loaded) == 2
    assert loaded[0].key == "o-1a"
    assert loaded[1].key == "dex"


def test_promote_idempotency(tmp_registry_and_topics: tuple[SliceRegistry, Path]) -> None:
    """Test that promoting an already-registered slug doesn't duplicate it."""
    registry, topics_dir = tmp_registry_and_topics

    # Create fake topic pages
    (topics_dir / "o-1a.md").write_text("---\ntitle: O-1A Model\n---\nContent here.")
    (topics_dir / "ntrp.md").write_text("---\ntitle: NTRP System\n---\nMore content.")

    # Promote o-1a first time
    result1 = promote(registry, topics_dir, ["o-1a"])
    assert len(result1) == 1
    assert result1[0].key == "o-1a"

    # Promote both o-1a and ntrp
    result2 = promote(registry, topics_dir, ["o-1a", "ntrp"])

    # Should only add ntrp, not duplicate o-1a
    assert len(result2) == 2
    keys = [s.key for s in result2]
    assert keys.count("o-1a") == 1, "o-1a should not be duplicated"
    assert "ntrp" in keys

    # Verify final state in registry
    loaded = registry.load()
    assert len(loaded) == 2
    keys = [s.key for s in loaded]
    assert keys == ["o-1a", "ntrp"]


def test_promote_uses_slug_as_fallback_title(tmp_registry_and_topics: tuple[SliceRegistry, Path]) -> None:
    """Test that slug is used as title if frontmatter title is missing."""
    registry, topics_dir = tmp_registry_and_topics

    # Create a page with no title frontmatter
    (topics_dir / "aside.md").write_text("---\nupated: 2026-07-07\n---\nNo title here.")

    result = promote(registry, topics_dir, ["aside"])

    assert len(result) == 1
    assert result[0].key == "aside"
    assert result[0].title == "aside"  # Falls back to slug


def test_promote_empty_slug_list_returns_empty(tmp_registry_and_topics: tuple[SliceRegistry, Path]) -> None:
    """Test that promoting with empty slug list returns empty result."""
    registry, topics_dir = tmp_registry_and_topics

    result = promote(registry, topics_dir, [])

    assert len(result) == 0
    loaded = registry.load()
    assert len(loaded) == 0
