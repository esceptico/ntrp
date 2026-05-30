"""Lens loader.

A *lens* is an instruction file that declares a memory "directory" (a named
grouping like "thirdlayer engineers") and tells the memory automation how to
classify entities into it and how to shape each member's profile. Lenses never
store data — the graph (memory_items + member_of edges) is canonical; lens
files only have authority over how that data gets shaped.

Files live in ``~/.ntrp/memory/lenses/<slug>.md`` with YAML frontmatter:

    ---
    directory: thirdlayer engineers
    entity_type: person
    ---
    ## Belongs
    Engineers who work at thirdlayer — Kevin, Chris, me.

    ## Profile shape
    - Role / what they own
    - How I work with them
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ntrp.logging import get_logger
from ntrp.settings import NTRP_DIR

_logger = get_logger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
# slug: lowercase letters, digits, hyphens; must start with a letter.
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def get_lenses_dir() -> Path:
    return NTRP_DIR / "memory" / "lenses"


@dataclass(slots=True)
class Lens:
    slug: str
    directory: str
    entity_type: str
    body: str
    path: Path


def _parse(content: str) -> tuple[dict, str] | None:
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    try:
        frontmatter = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict):
        return None
    return frontmatter, content[m.end() :]


def load_lenses(lenses_dir: Path | None = None) -> list[Lens]:
    base = lenses_dir or get_lenses_dir()
    if not base.is_dir():
        return []
    lenses: list[Lens] = []
    seen: set[str] = set()
    for path in sorted(base.glob("*.md")):
        slug = path.stem
        if not _SLUG_RE.match(slug):
            _logger.warning("Skipping lens %s: invalid slug", path)
            continue
        parsed = _parse(path.read_text(encoding="utf-8"))
        if parsed is None:
            _logger.warning("Skipping lens %s: invalid frontmatter", path)
            continue
        frontmatter, body = parsed
        directory = frontmatter.get("directory")
        entity_type = frontmatter.get("entity_type")
        if not isinstance(directory, str) or not directory.strip():
            _logger.warning("Skipping lens %s: missing 'directory'", path)
            continue
        if not isinstance(entity_type, str) or not entity_type.strip():
            _logger.warning("Skipping lens %s: missing 'entity_type'", path)
            continue
        if slug in seen:
            _logger.warning("Skipping lens %s: duplicate slug", path)
            continue
        seen.add(slug)
        lenses.append(
            Lens(
                slug=slug,
                directory=directory.strip(),
                entity_type=entity_type.strip(),
                body=body.strip(),
                path=path,
            )
        )
    return lenses
