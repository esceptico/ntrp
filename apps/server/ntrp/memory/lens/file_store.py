"""LensFileStore — lens DEFINITIONS as editable markdown files on disk.

A lens DEFINITION is a file the user opens and edits directly, never a DB row.
Files live at ``NTRP_DIR/memory/lenses/<slug>.md`` with YAML frontmatter plus a
``## Belongs`` section (the membership criterion in prose) and an optional
``## Profile shape`` section (the fields each member's profile captures):

    ---
    directory: thirdlayer engineers
    entity_type: person
    scope: user
    render_mode: grouped_by_subject
    detail_level: structured
    provenance: user_authored
    ---
    ## Belongs
    Engineers who work at thirdlayer — Kevin, Chris, me.

    ## Profile shape
    - Role / what they own
    - How I work with them

This store reads/lists/writes/deletes those files and nothing else. It owns NO
membership computation, NO claims, NO graph. The computed membership cache lives
in the DB keyed by the lens SLUG; files are the sole source of truth for the
definition. No keyword/regex/threshold gate decides anything here — parsing is
purely structural.
"""

import re
from pathlib import Path

import yaml

from ntrp.logging import get_logger
from ntrp.memory.models import (
    LensDetailLevel,
    LensProvenance,
    LensRenderMode,
    LensRow,
    LensStatus,
    Scope,
    ScopeKind,
)

_logger = get_logger(__name__)

# Frontmatter: a leading ``---`` block; body is everything after the closing ---.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
# slug: lowercase letters, digits, hyphens; must start with a letter.
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_BELONGS_RE = re.compile(r"^##\s+Belongs\s*$", re.MULTILINE | re.IGNORECASE)
_PROFILE_RE = re.compile(r"^##\s+Profile shape\s*$", re.MULTILINE | re.IGNORECASE)


def slugify(value: str) -> str:
    """Derive a file slug from a directory name. Slug rules from the old lenses.py:
    lowercase, hyphen-separated, must start with a letter. Structural only."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64]
    slug = slug.lstrip("0123456789-") or "lens"
    return slug if _SLUG_RE.match(slug) else "lens"


def compose_body(belongs: str, profile_shape: list[str]) -> str:
    """The editable markdown body: a ``## Belongs`` section + optional ``## Profile
    shape`` bullet list. This is the lens `criterion` the membership judge reads
    and the projector shapes profiles from."""
    parts = [f"## Belongs\n{belongs.strip()}"]
    fields = [f.strip() for f in profile_shape if f and f.strip()]
    if fields:
        parts.append("## Profile shape\n" + "\n".join(f"- {f}" for f in fields))
    return "\n\n".join(parts)


def render_lens_markdown(lens: LensRow) -> str:
    """Render a LensRow to the on-disk file format: YAML frontmatter + body.

    `name` is the directory; `criterion` is the already-composed Belongs/Profile
    body. render_mode/detail_level/provenance/scope live in the frontmatter so the
    user can edit them in place.
    """
    front = {
        "directory": lens.name,
        "entity_type": lens.entity_type,
        "scope": str(lens.scope.kind),
        "render_mode": str(lens.render_mode),
        "detail_level": str(lens.detail_level),
        "provenance": str(lens.provenance),
    }
    if lens.scope.key:
        front["scope_key"] = lens.scope.key
    # Persist timestamps so created_at is stable across edits (mtime would make it
    # jump to the last edit and reshuffle the lens list).
    front["created_at"] = lens.created_at
    front["updated_at"] = lens.updated_at
    # Serialize with yaml.dump, NOT string concat: a free-text directory/name
    # containing ":" or a newline (e.g. "Project X: Q3 goals") would otherwise
    # produce invalid YAML, and the read path silently drops an unparseable file —
    # the lens would vanish on next load. yaml.dump quotes/escapes such values.
    frontmatter = yaml.dump(front, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{frontmatter}---\n{lens.criterion.strip()}\n"


class LensFileStore:
    """Reads/lists/writes/deletes lens definition files in one directory.

    The directory is injected so tests use a tmp dir and never touch
    ``~/.ntrp/memory/lenses``.
    """

    def __init__(self, lenses_dir: Path):
        self.lenses_dir = lenses_dir

    # --- read ---------------------------------------------------------

    def read(self, slug: str) -> LensRow | None:
        path = self.lenses_dir / f"{slug}.md"
        if not _SLUG_RE.match(slug) or not path.is_file():
            return None
        return self._parse_file(slug, path)

    def list(self) -> list[LensRow]:
        if not self.lenses_dir.is_dir():
            return []
        out: list[LensRow] = []
        seen: set[str] = set()
        for path in sorted(self.lenses_dir.glob("*.md")):
            slug = path.stem
            if not _SLUG_RE.match(slug) or slug in seen:
                continue
            lens = self._parse_file(slug, path)
            if lens is not None:
                seen.add(slug)
                out.append(lens)
        return out

    # --- write / delete -----------------------------------------------

    def write(self, lens: LensRow) -> LensRow:
        self.lenses_dir.mkdir(parents=True, exist_ok=True)
        (self.lenses_dir / f"{lens.id}.md").write_text(
            render_lens_markdown(lens), encoding="utf-8"
        )
        return lens

    @staticmethod
    def valid_slug(slug: str) -> bool:
        return bool(_SLUG_RE.match(slug))

    def delete(self, slug: str) -> bool:
        # Validate the slug like read()/list() do — an unvalidated slug like
        # `../../foo` would unlink a .md file outside the lenses dir (the lens tool
        # passes an LLM-supplied lens_id straight through).
        if not self.valid_slug(slug):
            return False
        path = self.lenses_dir / f"{slug}.md"
        if not path.is_file():
            return False
        path.unlink()
        return True

    # --- parsing (structural only) ------------------------------------

    def _parse_file(self, slug: str, path: Path) -> LensRow | None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            _logger.warning("lens file %s unreadable: %s", path, e)
            return None
        m = _FRONTMATTER_RE.match(content)
        if not m:
            _logger.warning("lens %s: missing frontmatter", path)
            return None
        try:
            front = yaml.safe_load(m.group(1))
        except yaml.YAMLError as e:
            _logger.warning("lens %s: bad frontmatter yaml: %s", path, e)
            return None
        if not isinstance(front, dict):
            return None

        directory = front.get("directory")
        entity_type = front.get("entity_type")
        if not isinstance(directory, str) or not directory.strip():
            _logger.warning("lens %s: missing 'directory'", path)
            return None
        if not isinstance(entity_type, str) or not entity_type.strip():
            _logger.warning("lens %s: missing 'entity_type'", path)
            return None

        body = content[m.end():].strip()
        try:
            scope = self._scope(front)
        except ValueError as e:
            # A hand-edited PROJECT/SESSION lens missing scope_key would otherwise
            # raise out of read()/list() and break loading of EVERY lens. Skip just
            # this one, like the other malformed-frontmatter guards above.
            _logger.warning("lens %s: invalid scope: %s", path, e)
            return None
        # Prefer persisted timestamps; fall back to mtime only for legacy files that
        # predate timestamp persistence. (mtime alone makes created_at jump to the
        # last edit and reshuffles the lens list — fixed by writing them out.)
        mtime = self._mtime_iso(path)
        created = front.get("created_at") if isinstance(front.get("created_at"), str) else mtime
        updated = front.get("updated_at") if isinstance(front.get("updated_at"), str) else mtime
        return LensRow(
            id=slug,
            name=directory.strip(),
            criterion=body,
            scope=scope,
            entity_type=entity_type.strip(),
            detail_level=self._enum(LensDetailLevel, front.get("detail_level"), LensDetailLevel.STRUCTURED),
            render_mode=self._enum(LensRenderMode, front.get("render_mode"), LensRenderMode.FLAT),
            provenance=self._enum(LensProvenance, front.get("provenance"), LensProvenance.USER_AUTHORED),
            status=LensStatus.ACTIVE,
            page=None,
            created_at=created,
            updated_at=updated,
        )

    @staticmethod
    def _scope(front: dict) -> Scope:
        raw = front.get("scope")
        try:
            kind = ScopeKind(raw) if raw else ScopeKind.USER
        except ValueError:
            kind = ScopeKind.USER
        key = front.get("scope_key") if kind is not ScopeKind.USER else None
        return Scope(kind=kind, key=key)

    @staticmethod
    def _enum(enum_cls, raw, default):
        if not isinstance(raw, str):
            return default
        try:
            return enum_cls(raw.strip())
        except ValueError:
            return default

    @staticmethod
    def _mtime_iso(path: Path) -> str:
        from datetime import UTC, datetime

        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
