"""Seed registry CLI: list candidate topic pages and promote selected ones to slices."""

import sys
from datetime import datetime
from pathlib import Path

from ntrp.config import Config
from ntrp.constants import SLICES_FILE
from ntrp.memory.pages import parse_page
from ntrp.slices.models import Slice
from ntrp.slices.registry import SliceRegistry


def promote(registry: SliceRegistry, topics_dir: Path, slugs: list[str]) -> list[Slice]:
    """Promote topic pages to slices.

    Args:
        registry: SliceRegistry instance
        topics_dir: Path to topics directory
        slugs: List of topic slugs to promote

    Returns:
        Updated list of all slices after promotion
    """
    if not slugs:
        return []

    # Load current slices
    slices = registry.load()
    existing_keys = {s.key for s in slices}

    # Promote new slices
    for slug in slugs:
        if slug in existing_keys:
            continue  # Already registered; skip

        topic_file = topics_dir / f"{slug}.md"
        if not topic_file.exists():
            continue  # Topic file doesn't exist; skip

        # Parse the page to extract title
        content = topic_file.read_text()
        page = parse_page(content)
        title = page.frontmatter.get("title", slug)

        # Create and add slice
        slice_ = Slice(
            key=slug,
            title=title,
            page_path=f"topics/{slug}.md",
            autonomy="observe",
        )
        slices.append(slice_)
        existing_keys.add(slug)

    # Save and return
    registry.save(slices)
    return slices


def _format_date(path: Path) -> str:
    """Format file's mtime as YYYY-MM-DD."""
    if not path.exists():
        return "unknown"
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def main() -> None:
    """CLI entry point: list topics and optionally promote them."""
    config = Config()
    topics_dir = config.memory_artifacts_dir / "topics"
    registry_file = config.ntrp_dir / SLICES_FILE
    registry = SliceRegistry(registry_file)

    # Load current slices
    registered = {s.key for s in registry.load()}

    # List all topic pages
    if not topics_dir.exists():
        print(f"Topics dir not found: {topics_dir}")
        return

    topics = sorted(topics_dir.glob("*.md"))
    if not topics:
        print("No topic pages found")
        return

    print(f"Found {len(topics)} topic pages:\n")
    for topic in topics:
        slug = topic.stem
        page = parse_page(topic.read_text())
        title = page.frontmatter.get("title", slug)
        updated = _format_date(topic)
        status = "✓ registered" if slug in registered else "  candidate "
        print(f"  {status}  {slug:20} | {title:40} | {updated}")

    # If slugs provided, promote them
    if len(sys.argv) > 1:
        slugs = sys.argv[1:]
        print(f"\nPromoting {len(slugs)} slice(s)...")
        result = promote(registry, topics_dir, slugs)
        print(f"Registry now contains {len(result)} slice(s)")
        registered = {s.key for s in result}
        print("\nUpdated registry:")
        for s in result:
            status = "new" if s.key in sys.argv[1:] else "existing"
            print(f"  [{status:8}]  {s.key:20} | {s.title}")


if __name__ == "__main__":
    main()
