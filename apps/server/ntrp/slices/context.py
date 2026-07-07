from pathlib import Path

from ntrp.memory.pages import parse_page
from ntrp.slices.registry import SliceRegistry


def load_slice_context(registry_path: Path, vault_dir: Path, key: str) -> dict | None:
    """Prompt context for a slice-tagged chat: the slice's title + topic
    page prose. None when the key is unknown or the page is missing —
    a scoped chat degrades to a plain chat rather than failing the run."""
    try:
        slice_ = SliceRegistry(registry_path).get(key)
    except KeyError:
        return None
    page_file = vault_dir / slice_.page_path
    if not page_file.exists():
        return None
    page = parse_page(page_file.read_text())
    return {"title": slice_.title, "page": page.prose.strip()}
