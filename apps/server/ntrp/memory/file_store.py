"""FilePageStore — canonical memory backed by plain markdown two-zone pages.

Duck-types the slice of RecordStore that tools/profile/curator actually call
(open/close/attach_search_index, add/update/supersede_with/supersede/confirm/
set_pinned/delete, set_labels/labels_for/labels_of/list_labels, get/search/list/
count_active). Mounted under MEMORY_RECORDS_SERVICE in place of RecordStore so
canonicality flips with one assignment — no tool, prompt, or scope changes.

Retrieval is an in-memory token-overlap scan: at ~80 records this beats any index
(ponytail: no sqlite-vec, no FTS DB, no refresh-on-write bookkeeping). The .md
files are the single source of truth; nothing here is derived state to reconcile.
No git: durability is the files themselves + an external backup before destructive
passes.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from ntrp.constants import MEMORY_MIN_ENTITY_RECORDS, RRF_K
from ntrp.database import serialize_embedding
from ntrp.logging import get_logger
from ntrp.memory.models import TRUST_DEFAULT, TRUST_LEVEL, Kind, Record, SourceRef, now_iso
from ntrp.memory.pages import Line, Page, parse_page, render_page
from ntrp.memory.scorer import salience
from ntrp.search.retrieval import rrf_merge

_logger = get_logger(__name__)

_MEMORY_LINE_SOURCE = "memory_line"  # search.db partition for per-line vectors (own source, never transcripts)
_DIRECTIVES = "directives.md"
_REFERENCES = "references.md"
_ME = "me.md"
_LESSONS = "lessons.md"  # continual-learning playbook (distilled lesson records)
_ENTITIES = "topics"  # one folder for every emergent subject (people/products/projects/topics)
_LEGACY_SUBJECT_DIRS = ("entities", "projects")  # folded into topics/ at open() (migration)
_OBSERVATIONS = "observations"  # per-source raw integration stream (gmail/slack/calendar), dream-mined
_INSIGHTS = "insights"  # cross-domain DREAM outputs (OKF insights/), kept out of facts/entities
_GENERATED_FILES = {"index.md", "AGENTS.md", "health.md"}  # generated reports, not record pages
# Canonical, properly-cased titles for the fixed structural pages (root). Keeps the
# index + Obsidian note titles clean ("Me", not "me") and self-heals contamination.
_STRUCTURAL_TITLES = {
    _ME: "Me",
    _DIRECTIVES: "Directives",
    _LESSONS: "Playbook",
    _REFERENCES: "References",
    "active-work.md": "Active work",
}

_CONVENTIONS_TEMPLATE = """\
# Memory conventions (AGENTS.md)

This directory is a personal memory wiki — plain markdown, the single source of
truth (no DB). An agent reads it to understand the user and act on their behalf.

## Page format (two zones)
Each page is synthesized **prose** above a sentinel, then an append-only
**timeline** of atomic records below it:

    <compiled prose — the current, human-readable briefing>
    <!-- timeline (append-only; edit prose above, not below) -->
    - 2026-06-21 ^a1b2c3d4 [fact] [imp:6] (src:curator) Tim rides a gravel bike.

A timeline line is the canonical record. Tags: `[pin]` (never dropped),
`[imp:1-10]` (poignancy), `[ent:slug]` (primary entity), `[superseded]`.
`(src:…)` is provenance. The prose cites records as `(record:<8hex>)`.

## Record kinds (by FUNCTION, not subject)
- `directive` — a standing behaviour rule the USER stated.
- `fact` — a stable, durable truth about the user or their world.
- `source` — a re-findable pointer (receipt), evidence for a fact.
- `lesson` — a working-pattern the agent DISTILLED (the continual-learning playbook).
- `observation` — a raw integration item (low-trust, ages out fast).
- `changelog` — housekeeping; ignore for synthesis.

## Layout
- `me.md` — the user's profile (root of the wiki).
- `directives.md` — standing behaviour rules.   `lessons.md` — learned playbook.
- `active-work.md` — current work, synthesized across the store.
- `topics/<slug>.md` — one page per emergent subject (people, products, projects,
  topics). A subject emerges once it has ≥2 records (else parked on me.md); a page
  with a `scope_key` is a project workstream. No separate people/ or projects/ split.
- `references.md` — source pointers.
- `observations/<source>.md` — raw integration streams (gmail/calendar/slack).
- `insights/<month>.md` — cross-domain dream outputs (provisional, cited).
- `daily/<date>.md` — per-day activity log, synthesized prose only (browsable history).
- `health.md` — generated self-audit of gaps (stale topics, idle sources).
- `.index/` — throwaway search index (rebuildable, never canonical).

Navigation is the file tree itself — the desktop file browser, Obsidian's explorer,
or the agent's memory_tree tool. There is no generated index file.

## Source trust
When sources conflict, the higher-trust source wins — update the claim in place. A
lower-trust source never overrides a higher one. Integration- and dream-sourced claims
are phrased tentatively; never launder them into user-stated confidence.

| trust | source | how to treat it |
|-------|--------|-----------------|
{trust_rows}

## Grounding
Cite only real record ids you were given — never invent, reformat, or guess one. Assert
only what the cited records support; bring in no outside knowledge. On conflict between
records: directive > fact > source. Pinned records are never dropped; changelog records
are ignored for synthesis. Never leak a record id or file path into user-facing prose.
Cite dialects: synthesized pages write `(record:<8hex>)`; dream insights write
`(because of ^id1, ^id2)`.

## Authoring
Re-read a page before editing it. Update prose IN PLACE — don't append corrections as new
sentences. Edit the prose ABOVE the sentinel, never the timeline below. Prune stale claims.
Two learnings channels — not parallel systems: `lessons.md` (the distilled, agent-facing
playbook) rides the resident profile into every turn; `.maintenance/<automation>-learnings.md`
holds per-automation operational notes read ONLY by that automation, never shown in chat.
"""


def _trust_rows() -> str:
    """Render the source-trust table FROM models.TRUST_LEVEL so the manual can't drift
    from the code that enforces it. Descending trust; the default tier (integration/
    unknown) is synthesized from TRUST_DEFAULT."""
    notes = {
        4: "direct statements & corrections — always win",
        3: "distilled from the user's own conversations",
        2: "passive signals — verify before acting",
        1: "inferred cross-domain — hold loosely",
    }
    tiers: dict[int, list[str]] = {TRUST_DEFAULT: ["integration:*", "unknown"]}
    for src, lvl in TRUST_LEVEL.items():
        tiers.setdefault(lvl, [])
        if src not in tiers[lvl]:
            tiers[lvl].append(src)
    return "\n".join(
        f"| {lvl} | {', '.join(tiers[lvl])} | {notes.get(lvl, 'weigh by trust level')} |"
        for lvl in sorted(tiers, reverse=True)
    )


def _build_conventions() -> str:
    return _CONVENTIONS_TEMPLATE.replace("{trust_rows}", _trust_rows())


_CONVENTIONS = _build_conventions()  # the written AGENTS.md AND what load_conventions() serves


def load_conventions() -> str:
    """The operating manual the maintenance LLM passes prepend as shared context — the
    same bytes _write_conventions() writes to AGENTS.md (single source of truth)."""
    return _CONVENTIONS


_PARKABLE = (_ME, _REFERENCES)  # generic pages whose records may promote to an entity page


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return s or "untitled"


def _deslug(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.split("-")) if slug else slug


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _norm(text: str) -> str:
    """Collapse whitespace (incl. newlines) — a timeline line is one physical line,
    so embedded newlines would otherwise truncate on reload."""
    return " ".join(text.split())


def _iso(date: str) -> str:
    return f"{date}T00:00:00+00:00" if date else now_iso()


class FilePageStore:
    def __init__(self, root: Path, search_index: object | None = None, project_names: dict[str, str] | None = None) -> None:
        self._root = Path(root)
        self._search_index = search_index  # optional semantic leg (search.db); lexical-only when None
        self._project_names = project_names or {}  # scope_key -> human project name (page naming)
        self._scorer = None  # optional async (text, kind, pinned) -> int(1..10); set by knowledge
        self._pages: dict[Path, Page] = {}
        self._loc: dict[str, Path] = {}  # record id -> page path

    # -- lifecycle -----------------------------------------------------------

    async def open(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._pages.clear()
        self._loc.clear()
        for path in sorted(self._root.rglob("*.md")):
            # Generated reports live at ROOT only; a nested file like topics/health.md
            # is a real content page (the user's "health" topic), not the generated audit.
            # .maintenance/ holds per-automation learnings sidecars — never record pages
            # (rglob DOES descend dotdirs, so this filter is mandatory).
            if {".index", ".maintenance"} & set(path.parts) or (path.parent == self._root and path.name in _GENERATED_FILES):
                continue  # .index/.maintenance = throwaway; root index.md/AGENTS.md/health.md = generated
            try:
                page = parse_page(path.read_text(encoding="utf-8"))
            except Exception:
                _logger.warning("skip unparseable memory page", path=str(path))
                continue
            self._pages[path] = page
            for line in page.lines:
                self._loc[line.id] = path
        self._migrate_insights()  # relocate pre-insights/ dream records (one-time, idempotent)
        self._migrate_to_topics()  # fold entities/+projects/ into one topics/ folder (idempotent)
        self._heal_structural_pages()  # repair cross-contaminated identity + canonical titles
        self._backfill_entities()
        stats = await self.reconcile_entities()
        self._write_conventions()  # AGENTS.md (OKF conventions) — static, once
        self._write_health()       # health.md (self-audit / surfaced gaps) — deterministic
        self._drop_index()         # the file browser IS the index; a static tree-of-files file is redundant
        _logger.info("file memory ready", pages=len(self._pages), lines=len(self._loc), root=str(self._root), **stats)
        await self._sync_index()

    async def close(self) -> None:
        return None

    def attach_search_index(self, search_index: object | None) -> None:
        self._search_index = search_index

    def attach_scorer(self, scorer) -> None:
        """scorer: async (text, kind, pinned) -> int(1..10). Set by knowledge wiring."""
        self._scorer = scorer

    # -- vector index sync (search.db partition; throwaway/derived) ----------

    def _track(self, coro) -> None:
        async def _run():
            try:
                await coro
            except Exception:
                _logger.warning("memory_line index op failed", exc_info=True)

        asyncio.ensure_future(_run())

    def _index_line(self, line: Line) -> None:
        if self._search_index is None or line.superseded or not line.text.strip():
            return
        self._track(
            self._search_index.upsert(
                source=_MEMORY_LINE_SOURCE,
                source_id=line.id,
                title=f"{line.kind} line",
                content=line.text,
                metadata={"record_id": line.id, "kind": line.kind},
            )
        )

    def _unindex_line(self, record_id: str) -> None:
        if self._search_index is None:
            return
        self._track(self._search_index.delete(_MEMORY_LINE_SOURCE, record_id))

    async def _sync_index(self) -> None:
        """Reconcile search.db vectors with current page state at open() (bulk).
        upsert hash-dedups, so unchanged lines cost a hash check and zero embeds."""
        index = self._search_index
        if index is None:
            return
        try:
            active: dict[str, Line] = {}
            for page in self._pages.values():
                for line in page.active_lines():
                    if line.text.strip():
                        active[line.id] = line
            indexed = await index.store.get_indexed_hashes(_MEMORY_LINE_SOURCE)
            for stale in set(indexed) - set(active):
                await index.delete(_MEMORY_LINE_SOURCE, stale)
            for line in active.values():
                await index.upsert(
                    source=_MEMORY_LINE_SOURCE,
                    source_id=line.id,
                    title=f"{line.kind} line",
                    content=line.text,
                    metadata={"record_id": line.id, "kind": line.kind},
                )
        except Exception:
            _logger.warning("memory_line index sync failed", exc_info=True)

    async def score_pending(self) -> int:
        """Backfill importance on unscored lines via the attached scorer. Off the
        hot path (curator sweep). No-op when no scorer is attached."""
        if self._scorer is None:
            return 0
        scored = 0
        for path, page in self._pages.items():
            dirty = False
            for line in page.lines:
                if line.superseded or line.imp is not None:
                    continue
                try:
                    line.imp = await self._scorer(line.text, line.kind, line.pinned)
                    dirty = True
                    scored += 1
                except Exception:
                    _logger.warning("importance scoring failed", exc_info=True)
            if dirty:
                self._persist(path)
        return scored

    # -- internals -----------------------------------------------------------

    def _new_id(self) -> str:
        while True:
            rid = uuid4().hex[:8]
            if rid not in self._loc:
                return rid

    def _entity_labels(self, path: Path) -> list[str]:
        return list(self._pages[path].frontmatter.get("entity_labels", [])) if path in self._pages else []

    def _meta_labels(self, path: Path) -> list[str]:
        return list(self._pages[path].frontmatter.get("meta_labels", [])) if path in self._pages else []

    def _scope_for(self, path: Path, kind: str) -> tuple[str | None, str | None]:
        try:
            rel = path.relative_to(self._root)
        except ValueError:
            rel = path
        # Scope is a property of the page (frontmatter scope_key), not its folder — a
        # project page and an emergent topic both live in topics/; only the scope_key
        # tells them apart. This keeps active-work's project view working after the
        # entities/+projects/ folders were unified.
        page = self._pages.get(path)
        key = page.frontmatter.get("scope_key") if page else None
        if key:
            return ("project", str(key))
        if kind in (Kind.DIRECTIVE, Kind.LESSON):
            return ("global", None)  # behaviour rules + distilled playbook apply everywhere
        return ("user", None)

    def _to_record(self, line: Line, path: Path) -> Record:
        scope_kind, scope_key = self._scope_for(path, line.kind)
        return Record(
            id=line.id,
            text=line.text,
            kind=line.kind,
            scope_kind=scope_kind,
            scope_key=scope_key,
            created_at=_iso(line.date),
            last_confirmed_at=_iso(line.date),
            superseded_by=("superseded" if line.superseded else None),
            pinned=line.pinned,
            source_ref=SourceRef(kind=line.src, ref=line.id),
        )

    def _entity_path(self, slug: str) -> Path:
        return self._root / _ENTITIES / f"{slug}.md"

    def _page_for(self, kind: str, scope_kind: str | None, scope_key: str | None) -> Path:
        """The BASE page for a fresh record by kind+scope. Entity placement is NOT
        decided here — an entity-labeled record lands on its base page (me/references)
        and is promoted to entities/<slug>.md only once the entity crosses
        MEMORY_MIN_ENTITY_RECORDS, via _reconcile_entity."""
        if kind == Kind.DIRECTIVE:
            return self._root / _DIRECTIVES
        if kind == Kind.LESSON:
            return self._root / _LESSONS
        if scope_kind == "project" and scope_key:
            return self._root / _ENTITIES / f"{_slug(self._project_names.get(scope_key, scope_key))}.md"
        if kind == Kind.SOURCE:
            return self._root / _REFERENCES
        return self._root / _ME

    def _park_path(self, line: Line) -> Path:
        """Where a sub-threshold entity record lives: its kind-appropriate generic
        page (references for source pointers, me.md otherwise)."""
        return self._root / (_REFERENCES if line.kind == Kind.SOURCE else _ME)

    def _entity_members(self, slug: str) -> list[tuple[Path, Line]]:
        return [(p, ln) for p, page in self._pages.items() for ln in page.lines if ln.entity == slug]

    def _entity_display(self, slug: str) -> str:
        """Human label for a slug: the entity page's title when one exists, else a
        de-slugged guess. Stable under slugify so the curator's reused label maps
        back to the same page."""
        ep = self._pages.get(self._entity_path(slug))
        return (ep.frontmatter.get("title") if ep else None) or _deslug(slug)

    def _reconcile_entity(self, slug: str | None, *, display: str | None = None) -> Path | None:
        """Place every record of one entity on the right page: its own
        entities/<slug>.md once the entity has >= MEMORY_MIN_ENTITY_RECORDS active
        records, else parked on its kind-appropriate generic page. Lifecycle follows
        the ACTIVE RECORD COUNT, not prose: a page's synthesized prose is a derived
        projection (regenerated nightly from the records), so folding a sub-threshold
        entity discards that prose while the canonical records move intact to me.md and
        re-synthesize there — no data is lost. Idempotent and write-frugal (persists
        only pages it changes); moves never touch the vector index (id+text unchanged)."""
        if not slug:
            return None
        entity_page = self._entity_path(slug)
        existing = self._pages.get(entity_page)
        members = self._entity_members(slug)
        if not members:
            # No records carry this slug (e.g. its last record was deleted) -> the page is
            # a dead file; drop it. Its prose described records that no longer exist.
            if existing is not None and not existing.lines:
                self._pages.pop(entity_page, None)
                entity_page.unlink(missing_ok=True)
            return None
        if display is None:
            display = (existing.frontmatter.get("title") if existing else None) or _deslug(slug)
        # A project page (frontmatter scope_key) is a real workstream — its lifecycle
        # follows the project, not the entity-tag count, so it is never demoted/parked.
        is_project = existing is not None and bool(existing.frontmatter.get("scope_key"))
        promoted = is_project or sum(1 for _, ln in members if not ln.superseded) >= MEMORY_MIN_ENTITY_RECORDS
        touched: set[Path] = set()
        for path, line in members:
            dest = entity_page if promoted else self._park_path(line)
            if path == dest:
                continue
            self._pages[path].lines = [ln for ln in self._pages[path].lines if ln.id != line.id]
            self._ensure_page(dest, title=(display if dest == entity_page else None)).lines.append(line)
            self._loc[line.id] = dest
            touched.add(path)
            touched.add(dest)
        if promoted:
            page = self._ensure_page(entity_page, title=display)
            want = sorted({*page.frontmatter.get("entity_labels", []), display})
            if page.frontmatter.get("title") != display or page.frontmatter.get("entity_labels") != want:
                page.frontmatter["title"] = display
                page.frontmatter["entity_labels"] = want
                touched.add(entity_page)  # frontmatter drift -> needs a write
        for p in touched:
            # A folded-away entity page with no records left is a dead file (its prose
            # regenerates for whichever page now holds the records); a promoted page
            # still holds its records so it survives this.
            if p.parent.name == _ENTITIES and not self._pages[p].lines:
                self._pages.pop(p, None)
                p.unlink(missing_ok=True)
            else:
                self._persist(p)
        return entity_page if promoted else None

    async def reconcile_entities(self) -> dict[str, int]:
        """Full sweep: enforce the promotion threshold for every entity. Cheap +
        deterministic (no LLM, no index churn). Run at open() and after retention
        so a supersede that thins a page folds it back the same night. Sweeps both
        the slugs carried by lines AND existing entity-page files, so a page emptied
        by delete/prune/wipe (no tagged line left to name it) still gets reclaimed."""
        tagged = {ln.entity for page in self._pages.values() for ln in page.lines if ln.entity}
        files = {p.stem for p in self._pages if p.parent.name == _ENTITIES and p.name not in ("index.md", "needs-triage.md")}
        slugs = sorted(tagged | files)
        existed = {s for s in slugs if self._entity_path(s) in self._pages}
        for slug in slugs:
            self._reconcile_entity(slug)
        now = {s for s in slugs if self._entity_path(s) in self._pages}
        return {"entities": len(slugs), "promoted": len(now - existed), "demoted": len(existed - now)}

    def _heal_structural_pages(self) -> None:
        """Repair page identity contamination, normalize structural titles, and keep
        Obsidian wikilinks resolvable. Idempotent: a `scope_key` belongs only to a
        project page, so strip it from any non-project page (a project-scoped directive
        used to stamp it onto the global directives.md); give the fixed root pages
        canonical, properly-cased titles; and ensure each page's human title is in its
        `aliases` so prose `[[Title]]` links resolve to the dash-slug filename in
        Obsidian (preserving any aliases the user added in the vault)."""
        for path, page in self._pages.items():
            rel = path.relative_to(self._root)
            changed = False
            # scope_key belongs only on a topics/ subject page; strip it elsewhere (a
            # project-scoped directive used to stamp it onto the global directives.md).
            if rel.parts[0] != _ENTITIES and page.frontmatter.pop("scope_key", None) is not None:
                changed = True
            want = _STRUCTURAL_TITLES.get(rel.name) if len(rel.parts) == 1 else None
            if want and page.frontmatter.get("title") != want:
                page.frontmatter["title"] = want
                changed = True
            title = page.frontmatter.get("title")
            if title:
                aliases = page.frontmatter.get("aliases") or []
                if isinstance(aliases, str):
                    aliases = [aliases]
                needs_alias = title.lower() != rel.stem  # Obsidian's case-insensitive match would miss
                if needs_alias and title not in aliases:
                    page.frontmatter["aliases"] = [*aliases, title]
                    changed = True
                elif not needs_alias and aliases == [title]:
                    # redundant auto-alias (e.g. "Dex" on dex.md) — Obsidian resolves it already; drop the noise
                    del page.frontmatter["aliases"]
                    changed = True
            if changed:
                self._persist(path)

    def _migrate_to_topics(self) -> None:
        """Fold the legacy entities/ + projects/ folders into one topics/ folder.
        The split was incoherent: projects/ pages existed only when a CHAT was tagged
        to a project workspace, while entities/ emerged from labels — so the same
        subject (e.g. Dex) landed in BOTH, and real workstreams (e.g. MATS) hid under
        entities/. A subject now has exactly one topics/<slug>.md; scope lives in
        frontmatter (scope_key), not the folder. Idempotent: a no-op once migrated."""
        legacy = [p for p in list(self._pages.keys()) if p.parent.name in _LEGACY_SUBJECT_DIRS]
        for src in legacy:
            page = self._pages[src]
            target = self._root / _ENTITIES / src.name
            if target == src:
                continue
            existing = self._pages.get(target)
            if existing is None:  # reparent
                self._pages[target] = page
                del self._pages[src]
                for ln in page.lines:
                    self._loc[ln.id] = target
                page.frontmatter["type"] = "project" if page.frontmatter.get("scope_key") else "topic"
                self._persist(target)
            else:  # collision (e.g. Dex as both entity + project) — merge onto one page
                existing.lines.extend(page.lines)
                for ln in page.lines:
                    self._loc[ln.id] = target
                for key in ("scope_key", "title", "aliases", "entity_labels", "meta_labels"):
                    if key not in existing.frontmatter and key in page.frontmatter:
                        existing.frontmatter[key] = page.frontmatter[key]
                existing.frontmatter["type"] = "project" if existing.frontmatter.get("scope_key") else "topic"
                del self._pages[src]
                self._persist(target)
            try:
                src.unlink()
            except OSError:
                pass
        for name in _LEGACY_SUBJECT_DIRS:  # drop the now-empty legacy folders
            d = self._root / name
            if d.is_dir() and not any(d.iterdir()):
                try:
                    d.rmdir()
                except OSError:
                    pass

    def _migrate_insights(self) -> None:
        """One-time/idempotent: dream insights used to file to entities/insights.md via
        [ent:Insights]; they now belong in insights/<month>.md. Relocate any stray
        src=dreamer record so the emptied entity page is then dropped by reconcile."""
        for path in list(self._pages.keys()):
            if path.parent.name == _INSIGHTS:
                continue
            page = self._pages.get(path)
            if page is None:
                continue
            movers = [ln for ln in page.lines if ln.src == "dreamer"]
            if not movers:
                continue
            page.lines = [ln for ln in page.lines if ln.src != "dreamer"]
            for ln in movers:
                ln.entity = None
                month = (ln.date or now_iso())[:7]
                dest = self._root / _INSIGHTS / f"{month}.md"
                self._ensure_page(dest, title=f"Insights {month}").lines.append(ln)
                self._loc[ln.id] = dest
                self._persist(dest)
            self._persist(path)

    def _backfill_entities(self) -> None:
        """One-time: entity pages predate the per-line `entity` tag. Stamp each
        entities/<slug>.md record with its page slug so the promotion model sees it."""
        for path, page in self._pages.items():
            if path.parent.name != _ENTITIES or path.name in ("index.md", "needs-triage.md"):
                continue
            slug = path.stem
            changed = False
            for line in page.lines:
                if line.entity is None:
                    line.entity = slug
                    changed = True
            if changed:
                self._persist(path)

    def _write_conventions(self) -> None:
        """AGENTS.md (OKF conventions) — how this memory dir is shaped, so any agent
        reading it understands the format. Deterministic; refreshed each open() so the
        doc never drifts from the code."""
        path = self._root / "AGENTS.md"
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != _CONVENTIONS:
            path.write_text(_CONVENTIONS, encoding="utf-8")

    def _drop_index(self) -> None:
        """Navigation is the file tree itself — the desktop file browser for a human,
        the memory_tree tool for the agent. A generated index.md that draws an ASCII
        tree of the same files is redundant (dex keeps one only because its agent has
        no file browser). Remove any leftover so it stops cluttering the vault."""
        legacy = self._root / "index.md"
        if legacy.exists():
            try:
                legacy.unlink()
            except OSError:
                pass

    def _write_health(self) -> None:
        """health.md — a deterministic self-audit that surfaces blind spots (doc
        principle 11): stale topics, idle integration sources, and whether the dream/
        synthesis have run. Makes gaps visible instead of silently rotting."""
        today = datetime.now(UTC).date()
        STALE_DAYS, IDLE_DAYS, DREAM_DAYS = 90, 14, 7

        def _age(d: str) -> int | None:
            try:
                return (today - date.fromisoformat(d[:10])).days
            except ValueError:
                return None

        records = [ln for pg in self._pages.values() for ln in pg.active_lines()]
        by_kind: dict[str, int] = {}
        for ln in records:
            by_kind[ln.kind] = by_kind.get(ln.kind, 0) + 1
        last_dream = max((ln.date for ln in records if ln.src == "dreamer"), default=None)
        last_synth = max((str(pg.frontmatter.get("prose_synced")) for pg in self._pages.values()
                          if pg.frontmatter.get("prose_synced")), default=None)

        gaps: list[str] = []
        dream_age = _age(last_dream) if last_dream else None  # None != 0 — don't let a same-day dream read as "never"
        if dream_age is None or dream_age > DREAM_DAYS:
            gaps.append(f"- Cross-domain dream hasn't run recently (last: {last_dream or 'never'}) — fewer net-new insights.")
        for path, pg in sorted(self._pages.items()):
            if path.parent.name == _ENTITIES:
                newest = max((ln.date for ln in pg.active_lines()), default="")
                a = _age(newest)
                if a is not None and a > STALE_DAYS:
                    gaps.append(f"- Stale topic: `topics/{path.stem}.md` — no update in {a}d (since {newest}).")
            elif path.parent.name == _OBSERVATIONS:
                newest = max((ln.date for ln in pg.active_lines()), default="")
                a = _age(newest)
                if a is not None and a > IDLE_DAYS:
                    gaps.append(f"- Idle source: `observations/{path.stem}.md` — nothing new in {a}d (sync/connection?).")

        parts = [
            "# Memory health", "",
            f"{len(records)} active records across {len(self._pages)} pages — "
            + (", ".join(f"{k} {v}" for k, v in sorted(by_kind.items())) or "empty"),
            "",
            f"Last synthesis: {last_synth or 'never'} · last dream: {last_dream or 'never'}",
            "", "## Gaps", "",
            *(sorted(gaps) or ["- None — memory is current."]),
            "", "_Contradiction detection (conflicting records) is a future LLM-assisted check._",
        ]
        (self._root / "health.md").write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

    def _ensure_page(self, path: Path, *, title: str | None = None) -> Page:
        page = self._pages.get(path)
        if page is None:
            try:
                rel = path.relative_to(self._root)
            except ValueError:
                rel = path
            page_type = {"entities": "entity", "projects": "project"}.get(rel.parts[0], "topic") if len(rel.parts) > 1 else "topic"
            canonical = _STRUCTURAL_TITLES.get(rel.name) if len(rel.parts) == 1 else None
            resolved = title or canonical or path.stem
            fm = {"type": page_type, "title": resolved, "updated": now_iso()[:10]}
            if resolved.lower() != path.stem:  # only when Obsidian's case-insensitive filename match fails
                fm["aliases"] = [resolved]  # e.g. [[Interaction Lab]] -> interaction-lab.md (not for "Dex"->dex.md)
            page = Page(frontmatter=fm)
            self._pages[path] = page
        return page

    def _persist(self, path: Path) -> None:
        page = self._pages[path]
        page.frontmatter["updated"] = now_iso()[:10]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(render_page(page), encoding="utf-8")
        tmp.replace(path)

    def _find(self, record_id: str) -> tuple[Path, Line] | None:
        path = self._loc.get(record_id)
        if path is None:
            return None
        for line in self._pages[path].lines:
            if line.id == record_id:
                return path, line
        return None

    def _append(self, path: Path, line: Line, *, title: str | None = None) -> None:
        page = self._ensure_page(path, title=title)
        page.lines.append(line)
        self._loc[line.id] = path
        self._persist(path)

    # -- writes --------------------------------------------------------------

    async def add(
        self,
        text: str,
        *,
        kind: str = Kind.FACT,
        pinned: bool = False,
        source_ref: SourceRef | None = None,
        scope_kind: str | None = None,
        scope_key: str | None = None,
        record_id: str | None = None,
        entity_labels: list[str] | None = None,
        date: str | None = None,
    ) -> Record:
        rid = record_id or self._new_id()
        line = Line(
            id=rid,
            text=_norm(text),
            kind=str(kind),
            date=(date or now_iso())[:10],
            src=(source_ref.kind if source_ref else "unknown"),
            pinned=pinned,
        )
        if source_ref is not None and source_ref.kind == "dreamer":
            # Cross-domain dream insights get their own dated folder (OKF insights/),
            # separate from facts/entities; retention ages them as provisional.
            base = self._root / _INSIGHTS / f"{line.date[:7]}.md"
            title = f"Insights {line.date[:7]}"
        elif str(kind) == Kind.OBSERVATION and source_ref is not None:
            # Raw integration observations stream to a per-source page (never entity
            # pages, no promotion); the dream mines them across sources and retention
            # ages them out. A distinct page per source keeps cross-source insights
            # citing >=2 different pages (the dream's bar).
            base = self._root / _OBSERVATIONS / f"{_slug(source_ref.kind)}.md"
            title = source_ref.kind
        else:
            base = self._page_for(str(kind), scope_kind, scope_key)
            primary = _slug(entity_labels[0]) if entity_labels else None
            if primary and base.name in _PARKABLE:
                line.entity = primary  # remembered even while parked, so a later record can promote it
            # A project-scoped directive/lesson routes to the GLOBAL directives.md/
            # lessons.md by kind — its project identity must NOT stamp that page. Only a
            # subject page in topics/ takes the project title/scope_key.
            on_project_page = scope_kind == "project" and scope_key and base.parent.name == _ENTITIES
            title = self._project_names.get(scope_key, scope_key) if on_project_page else None
        self._append(base, line, title=title)
        # Persist the raw project key so non-slug-safe keys round-trip (the filename
        # is a lossy slug; _scope_for reads scope_key from frontmatter). Only on the
        # actual topics/ subject page — never on a global page a project rule landed on.
        if scope_kind == "project" and scope_key and base.parent.name == _ENTITIES:
            self._pages[base].frontmatter["scope_key"] = scope_key
            self._pages[base].frontmatter["type"] = "project"
            self._persist(base)
        self._index_line(line)
        if line.entity:
            final = self._reconcile_entity(line.entity, display=entity_labels[0]) or base
        else:
            final = base
            if entity_labels:  # project/directive-scoped + entity-labeled: tag the page, don't move it
                self._merge_labels(base, entity=entity_labels)
        return self._to_record(line, final)

    async def supersede(self, old_id: str, new_id: str) -> bool:
        found = self._find(old_id)
        if not found:
            return False
        path, line = found
        line.superseded = True
        self._persist(path)
        self._unindex_line(old_id)
        return True

    async def supersede_with(
        self,
        old_id: str,
        *,
        text: str,
        kind: str = Kind.FACT,
        source_ref: SourceRef | None = None,
        scope_kind: str | None = None,
        scope_key: str | None = None,
    ) -> Record:
        found = self._find(old_id)
        old_entity = found[1].entity if found else None
        old_display = self._pages[found[0]].frontmatter.get("title") if (found and found[0].parent.name == _ENTITIES) else None
        # Add the successor FIRST: a failure mid-op then leaves a harmless duplicate
        # rather than an old record superseded with no replacement (data loss).
        record = await self.add(text, kind=kind, source_ref=source_ref, scope_kind=scope_kind, scope_key=scope_key)
        if found:
            old_path, old_line = found
            old_line.superseded = True
            self._persist(old_path)
            self._unindex_line(old_id)
        if old_entity:
            succ = self._find(record.id)
            if succ and succ[1].entity is None:
                succ[1].entity = old_entity
                self._persist(succ[0])
            self._reconcile_entity(old_entity, display=old_display)  # place successor + fold the now-thinner old page
        return record

    async def set_kind(self, record_id: str, kind: str) -> bool:
        found = self._find(record_id)
        if not found:
            return False
        path, line = found
        line.kind = str(kind)
        self._persist(path)
        return True

    async def confirm(self, record_id: str) -> bool:
        found = self._find(record_id)
        if not found:
            return False
        path, line = found
        line.date = now_iso()[:10]
        self._persist(path)
        return True

    async def set_pinned(self, record_id: str, pinned: bool) -> bool:
        found = self._find(record_id)
        if not found:
            return False
        path, line = found
        line.pinned = bool(pinned)
        self._persist(path)
        return True

    async def update(self, record_id: str, text: str) -> bool:
        found = self._find(record_id)
        if not found:
            return False
        path, line = found
        line.text = _norm(text)
        line.date = now_iso()[:10]
        line.imp = None  # text changed -> re-score on next sweep
        self._persist(path)
        self._index_line(line)
        return True

    async def delete(self, record_id: str) -> None:
        found = self._find(record_id)
        if not found:
            return
        path, line = found
        entity = line.entity
        self._pages[path].lines = [ln for ln in self._pages[path].lines if ln.id != record_id]
        self._loc.pop(record_id, None)
        self._persist(path)
        self._unindex_line(record_id)
        if entity:  # a delete that drops a topic below the threshold must fold it now, not next sweep
            self._reconcile_entity(entity)

    async def prune(self) -> dict[str, int]:
        """Hard-delete tombstoned (superseded) lines from their pages + evict their
        vectors. Idempotent: a store with no superseded lines prunes nothing."""
        removed = 0
        for path, page in list(self._pages.items()):
            dead = [ln for ln in page.lines if ln.superseded]
            if not dead:
                continue
            page.lines = [ln for ln in page.lines if not ln.superseded]
            for ln in dead:
                self._loc.pop(ln.id, None)
                self._unindex_line(ln.id)
                removed += 1
            self._persist(path)
        return {"records": removed}

    async def wipe_except_pinned(self) -> dict[str, int]:
        """/init re-derivation primitive: delete every non-pinned line across all
        pages, keeping pinned survivors. Mirrors RecordStore.wipe_except_pinned."""
        deleted = kept = 0
        for path, page in list(self._pages.items()):
            keep = [ln for ln in page.lines if ln.pinned]
            drop = [ln for ln in page.lines if not ln.pinned]
            kept += len(keep)
            if not drop:
                continue
            page.lines = keep
            for ln in drop:
                self._loc.pop(ln.id, None)
                self._unindex_line(ln.id)
                deleted += 1
            self._persist(path)
        return {"deleted": deleted, "kept_pinned": kept}

    # -- labels --------------------------------------------------------------

    def _merge_labels(self, path: Path, *, entity: list[str] | None = None, meta: list[str] | None = None) -> None:
        page = self._ensure_page(path)
        if entity:
            cur = page.frontmatter.get("entity_labels", [])
            page.frontmatter["entity_labels"] = sorted({*cur, *entity})
        if meta:
            cur = page.frontmatter.get("meta_labels", [])
            page.frontmatter["meta_labels"] = sorted({*cur, *meta})
        self._persist(path)

    async def set_labels(self, record_id: str, labels: list[str], *, entity_labels: list[str] | None = None) -> None:
        found = self._find(record_id)
        if not found:
            return
        path, line = found
        primary = _slug(entity_labels[0]) if entity_labels else None
        # Entity-place only records on the generic pages or an existing entity page;
        # project/directive-scoped records keep their page (scope precedence).
        placeable = path.name in _PARKABLE or path.parent.name == _ENTITIES
        final, merge_entity = path, entity_labels
        if primary and placeable:
            old = line.entity
            line.entity = primary  # save the tag before reconcile, so a no-move park still records it
            self._persist(path)
            self._reconcile_entity(primary, display=entity_labels[0])
            final = self._loc.get(record_id, path)
            if old and old != primary:
                self._reconcile_entity(old)  # re-tag: fold the page it left if it went thin
            merge_entity = None  # promotion writes the entity_labels frontmatter; me.md stays clean
        if merge_entity or labels:
            self._merge_labels(final, entity=merge_entity, meta=labels)

    async def add_labels(self, record_id: str, labels: list[str], *, entity_labels: list[str] | None = None) -> None:
        await self.set_labels(record_id, labels, entity_labels=entity_labels)

    def _record_entities(self, path: Path, line: Line) -> list[str]:
        """Entity labels for one record: its per-line entity (so a sub-threshold record
        parked on me.md still surfaces its entity) plus any on the page frontmatter."""
        ents = list(self._entity_labels(path))
        if line.entity:
            ents.append(self._entity_display(line.entity))
        return ents

    async def labels_of(self, record_id: str) -> list[str]:
        found = self._find(record_id)
        if not found:
            return []
        path, line = found
        return sorted({*self._record_entities(path, line), *self._meta_labels(path)})

    async def labels_for(self, record_ids: list[str], *, include_kind: bool = False) -> dict:
        out: dict[str, list] = {}
        for rid in record_ids:
            found = self._find(rid)
            ents = sorted(set(self._record_entities(*found))) if found else []
            metas = self._meta_labels(found[0]) if found else []
            if include_kind:
                out[rid] = [{"label": l, "kind": "entity"} for l in ents] + [{"label": l, "kind": "meta"} for l in metas]
            else:
                out[rid] = sorted({*ents, *metas})
        return out

    async def list_labels(self) -> list[dict]:
        counts: dict[str, dict] = {}
        # Entity labels are counted per tagged active line — accurate per-entity
        # totals, including records still parked on me.md below the promotion threshold.
        for page in self._pages.values():
            for line in page.active_lines():
                if not line.entity:
                    continue
                label = self._entity_display(line.entity)
                row = counts.setdefault(label, {"label": label, "count": 0, "kind": "entity"})
                row["count"] += 1
        # Meta labels are page-level category tags (no per-line refinement).
        for path, page in self._pages.items():
            active = len(page.active_lines())
            if not active:
                continue
            for label in self._meta_labels(path):
                row = counts.setdefault(label, {"label": label, "count": 0, "kind": "meta"})
                if row["kind"] == "meta":
                    row["count"] += active
        return sorted(counts.values(), key=lambda r: (-r["count"], r["label"]))

    # -- consolidation primitives (the nightly Consolidate/dedup engine uses these) --

    async def neighborhood(self, record: Record, *, limit: int = 8) -> list[Record]:
        """Active records that resemble `record` (hybrid recall) minus itself — its
        consolidation neighborhood (the merge-candidate set)."""
        hits = await self.search(record.text, limit=limit + 1, scopes=None)
        return [h for h in hits if h.id != record.id][:limit]

    async def updated_since(self, watermark: str | None, *, limit: int) -> list[Record]:
        """The whole active pool, oldest-first. The `watermark` is intentionally NOT a
        skip filter: file records are DAY-granular ('<date>T00:00') with non-monotonic
        ids, so a finer-grained watermark would permanently skip records added after a
        same-day sweep. Returning the whole pool is correct + cheap because the consumer
        (Consolidate) skips unchanged neighborhoods via a content-fingerprint cache, so
        there's no per-night re-judging cost and no record-count ceiling."""
        recs = await self.list(limit=None, scopes=None)
        recs.sort(key=lambda r: (r.last_confirmed_at or "", r.id))
        return recs[:limit]

    async def merge(
        self, survivor_id: str, loser_ids: list[str], *, text: str | None = None, kind: str | None = None
    ) -> Record | None:
        """Collapse N records into ONE: each loser is superseded onto the survivor and
        evicted from the vector index; the survivor gains the union of all members' meta
        labels. `text` re-texts + re-confirms (re-scores) the survivor; `kind` retypes it.
        Aborts (None) if the survivor or ANY loser is pinned — pinned records are never
        merged away."""
        survivor = await self.get(survivor_id)
        if survivor is None or survivor.pinned:
            return None
        losers: list[Record] = []
        for lid in loser_ids:
            if lid == survivor_id:
                continue
            loser = await self.get(lid)
            if loser is None:
                continue
            if loser.pinned:
                return None  # never merge a pinned record away
            losers.append(loser)
        # Entity slugs touched by this merge — reconcile them after the losers are
        # superseded so a now-thin entity page folds (and the survivor's page is correct).
        sf = self._find(survivor_id)
        survivor_entity = sf[1].entity if sf else None
        slugs: set[str] = {survivor_entity} if survivor_entity else set()
        inherited_entity: str | None = None
        for loser in losers:
            lf = self._find(loser.id)
            if lf and lf[1].entity:
                slugs.add(lf[1].entity)
                if inherited_entity is None:
                    inherited_entity = self._entity_display(lf[1].entity)
        labels = await self.labels_for([survivor_id, *[lz.id for lz in losers]], include_kind=True)
        metas = sorted({e["label"] for entries in labels.values() for e in entries if e["kind"] == "meta"})
        if text is not None:
            await self.update(survivor_id, text)  # also re-confirms (sets date) + re-indexes
        if kind is not None:
            await self.set_kind(survivor_id, kind)
        # The survivor keeps its own entity; it inherits a loser's only if it had none,
        # so a uniquely-tagged loser isn't silently de-placed by the merge.
        ent_arg = [inherited_entity] if (inherited_entity and not survivor_entity) else None
        if metas or ent_arg:
            await self.set_labels(survivor_id, metas, entity_labels=ent_arg)
        for loser in losers:
            await self.supersede(loser.id, survivor_id)
        for slug in slugs:
            self._reconcile_entity(slug)
        return await self.get(survivor_id)

    async def rename_label(self, old: str, new: str) -> None:
        """Fold the label `old` into `new` (lint canonicalization) across meta labels
        and entity tags, then reconcile the entity pages that changed."""
        old_slug, new_slug = _slug(old), _slug(new)
        touched_pages: set[Path] = set()
        touched_slugs: set[str] = set()
        for path, page in self._pages.items():
            for key in ("meta_labels", "entity_labels"):
                vals = page.frontmatter.get(key)
                if vals and old in vals:
                    page.frontmatter[key] = sorted({(new if v == old else v) for v in vals})
                    touched_pages.add(path)
            for line in page.lines:
                if line.entity == old_slug:
                    line.entity = new_slug
                    touched_pages.add(path)
                    touched_slugs.update({old_slug, new_slug})
        for path in touched_pages:
            self._persist(path)
        for slug in touched_slugs:
            self._reconcile_entity(slug)

    async def set_label_kind(self, label: str, kind: str) -> int:
        """Retype a label between 'entity' and 'meta'. Only entity->meta is well-defined
        on the file model: untag the entity lines and record `label` as a page meta tag.
        meta->entity is a NO-OP — a page-level meta tag has no per-record membership to
        promote into per-line entity tags, so we leave it as meta rather than DELETE it
        (deleting without retagging would silently drop the label). Returns pages changed."""
        if kind != "meta":
            return 0  # meta->entity: can't faithfully map; leave the label untouched
        n = 0
        slug = _slug(label)
        for path, page in list(self._pages.items()):
            changed = False
            tagged = [ln for ln in page.lines if ln.entity == slug]
            if tagged:
                for ln in tagged:
                    ln.entity = None
                cur = page.frontmatter.get("meta_labels", [])
                page.frontmatter["meta_labels"] = sorted({*cur, label})
                changed = True
            ents = page.frontmatter.get("entity_labels")
            if ents and label in ents:
                page.frontmatter["entity_labels"] = [e for e in ents if e != label]
                changed = True
            if changed:
                self._persist(path)
                n += 1
        if slug:
            self._reconcile_entity(slug)
        return n

    # -- reads ---------------------------------------------------------------

    async def get(self, record_id: str) -> Record | None:
        found = self._find(record_id)
        return self._to_record(found[1], found[0]) if found else None

    def _iter_records(self, *, include_superseded: bool):
        for path, page in self._pages.items():
            for line in page.lines:
                if line.superseded and not include_superseded:
                    continue
                yield self._to_record(line, path)

    @staticmethod
    def _scope_ok(record: Record, scopes: list[tuple[str | None, str | None]] | None) -> bool:
        if scopes is None:
            return True
        for sk, sv in scopes:
            if sk == "global" and sv is None:
                if (record.scope_kind in (None, "global")) and record.scope_key is None:
                    return True
            elif record.scope_kind == sk and record.scope_key == sv:
                return True
        return False

    async def search(
        self,
        query: str,
        *,
        kinds: list[str] | None = None,
        limit: int = 10,
        include_superseded: bool = False,
        scopes: list[tuple[str | None, str | None]] | None = None,
    ) -> list[Record]:
        if scopes == []:
            return []
        q_tokens = _tokens(query)
        q_lower = query.lower().strip()
        window = max(limit * 8, 80)

        # Candidate lines (id -> (line, path)), honoring superseded visibility.
        cand: dict[str, tuple[Line, Path]] = {}
        for path, page in self._pages.items():
            for line in page.lines:
                if line.superseded and not include_superseded:
                    continue
                cand[line.id] = (line, path)

        # Lexical leg: token overlap + substring bonus. Kept dense (kind/scope
        # filtered AFTER fusion so RRF ranks stay stable).
        lex: list[tuple[str, float]] = []
        for rid, (line, _) in cand.items():
            tl = line.text.lower()
            score = float(len(q_tokens & _tokens(line.text)))
            if q_lower and q_lower in tl:  # query is a phrase IN the record (not the reverse:
                score += 5.0               # a 3-char record must not match every long query)
            if score > 0:
                lex.append((rid, score))
        lex.sort(key=lambda t: t[1], reverse=True)

        # Vector leg (search.db), best-effort; lexical-only on absence/failure.
        vec: list[tuple[str, float]] = []
        index = self._search_index
        if index is not None and q_lower:
            try:
                emb = await index.embedder.embed_one(query)
                raw = await index.store.vector_search(
                    serialize_embedding(emb), sources=[_MEMORY_LINE_SOURCE], limit=window
                )
                for item_id, vscore in raw:
                    item = await index.store.get_by_id(item_id)
                    meta = item.metadata if item and item.metadata else None
                    rid = meta.get("record_id") if meta else None
                    if rid in cand:
                        vec.append((rid, vscore))
            except Exception:
                _logger.warning("memory vector search failed; lexical-only", exc_info=True)

        # RRF-fuse the two legs, then rerank by salience (importance x recency).
        fused = rrf_merge([lex, vec], k=RRF_K)
        scored: list[tuple[float, str, Record]] = []
        for rid, rrf in fused.items():
            line, path = cand[rid]
            rec = self._to_record(line, path)
            if kinds and rec.kind not in kinds:
                continue
            if not self._scope_ok(rec, scopes):
                continue
            final = rrf * salience(line.imp, line.date)
            scored.append((final, rec.last_confirmed_at, rec))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [rec for _, _, rec in scored[:limit]]

    async def list(
        self,
        *,
        pinned_only: bool = False,
        include_superseded: bool = False,
        limit: int | None = 50,
        offset: int = 0,
        scopes: list[tuple[str | None, str | None]] | None = None,
        kinds: list[str] | None = None,
    ) -> list[Record]:
        if scopes == []:
            return []
        out = []
        for rec in self._iter_records(include_superseded=include_superseded):
            if pinned_only and not rec.pinned:
                continue
            if kinds and rec.kind not in kinds:
                continue
            if not self._scope_ok(rec, scopes):
                continue
            out.append(rec)
        out.sort(key=lambda r: r.last_confirmed_at, reverse=True)
        if limit is not None:
            out = out[offset : offset + limit]
        return out

    async def count_active(self) -> int:
        return sum(len(p.active_lines()) for p in self._pages.values())


if __name__ == "__main__":
    import asyncio
    import tempfile

    async def _demo():
        with tempfile.TemporaryDirectory() as d:
            store = FilePageStore(Path(d))
            await store.open()
            r1 = await store.add("Tim rides a gravel bike daily.", kind="fact", source_ref=SourceRef("user", ""))
            await store.set_labels(r1.id, [], entity_labels=["Bicycles"])
            await store.add("Always greet Tim by name.", kind="directive", source_ref=SourceRef("user", ""))
            await store.add("Tim's wife is Lena.", kind="fact", pinned=True, source_ref=SourceRef("user", ""))

            bike_page = Path(d) / "topics" / "bicycles.md"
            # ONE record for an entity must NOT spawn a topic page; it parks on me.md
            # remembering its entity so a second record can promote it later.
            assert not bike_page.exists(), "single-record entity must not get its own page"

            # reload from disk -> canonical files only
            store2 = FilePageStore(Path(d))
            await store2.open()
            assert await store2.count_active() == 3, await store2.count_active()
            assert not bike_page.exists(), "parked entity survives reload without a page"
            assert any(ln.entity == "bicycles" for p in store2._pages.values() for ln in p.lines), "entity tag persisted"
            # a parked sub-threshold record still surfaces its entity label (curator
            # vocabulary + UI), even though me.md frontmatter stays clean.
            assert await store2.labels_of(r1.id) == ["Bicycles"], await store2.labels_of(r1.id)
            assert any(r["label"] == "Bicycles" and r["count"] == 1 and r["kind"] == "entity" for r in await store2.list_labels())
            dirs = await store2.list(kinds=["directive"], scopes=[("global", None), ("user", None)])
            assert any("greet" in r.text for r in dirs), dirs
            pins = await store2.list(pinned_only=True, scopes=[("global", None), ("user", None)])
            assert any("Lena" in r.text for r in pins), pins
            hits = await store2.search("gravel bike", scopes=[("global", None), ("user", None)])
            assert hits and "gravel" in hits[0].text, hits

            # PROMOTION: a second Bicycles record crosses the threshold -> a real page
            # appears and BOTH records move onto it; the label browser now counts it.
            await store2.add("Tim's bike has 700c wheels.", kind="fact", source_ref=SourceRef("curator", ""), entity_labels=["Bicycles"])
            assert bike_page.exists(), "second record should promote the entity to its own page"
            promoted = FilePageStore(Path(d))
            await promoted.open()
            assert len(promoted._pages[bike_page].active_lines()) == 2, "both records move onto the promoted page"
            assert promoted._pages[bike_page].frontmatter.get("title") == "Bicycles"
            labels = await promoted.list_labels()
            assert any(r["label"] == "Bicycles" and r["count"] == 2 for r in labels), labels

            # supersede_with keeps the successor on the entity page (entity inherited).
            gravel_id = next(l.id for l in promoted._pages[bike_page].active_lines() if "gravel" in l.text)
            await promoted.supersede_with(gravel_id, text="Tim now rides a road bike.", source_ref=SourceRef("curator", ""))
            assert bike_page.exists() and len(promoted._pages[bike_page].active_lines()) == 2, "still 2 active -> stays promoted"

            # DEMOTION: drop active below the threshold -> page folds back, file removed.
            wheels_id = next(l.id for l in promoted._pages[bike_page].active_lines() if "700c" in l.text)
            await promoted.delete(wheels_id)
            await promoted.reconcile_entities()
            assert not bike_page.exists(), "page below threshold folds back to me.md and the dead file is dropped"

            again = FilePageStore(Path(d))
            await again.open()
            active_bike = [r for r in await again.list(scopes=None, limit=None) if "bike" in r.text]
            assert any("road bike" in r.text for r in active_bike)
            assert not any("gravel bike daily" in r.text for r in active_bike), "old line should be superseded"

            # DEMOTION follows ACTIVE RECORD COUNT, not prose: a synthesized dossier that
            # dips below the threshold folds back (its prose is a regenerable projection;
            # the canonical records survive on me.md and re-synthesize there).
            p1 = await again.add("Acme ships widgets.", kind="fact", source_ref=SourceRef("curator", ""), entity_labels=["Acme"])
            p2 = await again.add("Acme is based in Berlin.", kind="fact", source_ref=SourceRef("curator", ""), entity_labels=["Acme"])
            acme = Path(d) / "topics" / "acme.md"
            assert acme.exists() and len(again._pages[acme].active_lines()) == 2
            again._pages[acme].prose = f"Acme is a Berlin widget maker. (record:{p1.id})"  # simulate synthesis
            again._persist(acme)
            await again.delete(p2.id)  # 1 active < threshold -> demote
            await again.reconcile_entities()
            assert not acme.exists(), "sub-threshold entity folds back even with synthesized prose"
            assert any(ln.entity == "acme" for ln in again._pages[Path(d) / _ME].active_lines()), "record parked on me.md, tagged"

            # EMPTY PAGE RECLAIMED: deleting every record of a promoted entity leaves a
            # dead file; the sweep drops it (delete/prune/wipe don't reconcile themselves).
            q1 = await again.add("Zeta fact one.", kind="fact", source_ref=SourceRef("curator", ""), entity_labels=["Zeta"])
            q2 = await again.add("Zeta fact two.", kind="fact", source_ref=SourceRef("curator", ""), entity_labels=["Zeta"])
            zeta = Path(d) / "topics" / "zeta.md"
            assert zeta.exists()
            await again.delete(q1.id)
            await again.delete(q2.id)
            await again.reconcile_entities()
            assert not zeta.exists(), "empty entity page is reclaimed by the sweep"

            # OBSERVATION routing: a raw integration record streams to observations/<source>.md
            # (never an entity page), stays user-scoped + dream-listable.
            obs = await again.add("Email from Kevin re: PRD-407 review.", kind="observation", source_ref=SourceRef("gmail", "g1"))
            assert (Path(d) / "observations" / "gmail.md").exists(), "observation streams to observations/<source>.md"
            assert not (Path(d) / "topics" / "gmail.md").exists(), "observation never spawns an entity page"
            got = await again.get(obs.id)
            assert got.kind == "observation" and got.scope_kind == "user", (got.kind, got.scope_kind)
            assert any(r.id == obs.id for r in await again.list(scopes=None, limit=None)), "observation is dream-listable"

            # LESSON routing: continual-learning playbook records stream to lessons.md, global scope.
            les = await again.add("Verify against the running system before reporting status.", kind="lesson", source_ref=SourceRef("curator", ""))
            assert (Path(d) / "lessons.md").exists(), "lesson routes to lessons.md"
            lr = await again.get(les.id)
            assert lr.kind == "lesson" and lr.scope_kind == "global", (lr.kind, lr.scope_kind)

            # dream insights route to insights/<month>.md (OKF insights/), never me.md/entities
            ins = await again.add("Cross-domain insight.", kind="fact", source_ref=SourceRef("dreamer", "2026-06-23"))
            assert (await again.get(ins.id)).scope_kind == "user"
            assert any(p.parent.name == "insights" for p in again._pages), "dream insight filed under insights/"

            # conventions + self-audit are generated on open(). NO index.md: the file
            # tree itself (browser / memory_tree) is the navigation; a leftover is removed.
            assert (Path(d) / "AGENTS.md").exists(), "AGENTS.md conventions written"
            (Path(d) / "index.md").write_text("# stale\n", encoding="utf-8")
            once2 = FilePageStore(Path(d))
            await once2.open()
            assert not (Path(d) / "index.md").exists(), "redundant index.md removed, not regenerated"
            hp = Path(d) / "health.md"
            assert hp.exists() and "# Memory health" in hp.read_text(encoding="utf-8"), "health.md self-audit generated"

            # importance: heuristic scorer fills unscored lines, persists, survives reload
            async def _heur(text, kind, pinned):
                return 8 if pinned else 4

            again.attach_scorer(_heur)
            n = await again.score_pending()
            assert n > 0, n
            assert await again.score_pending() == 0, "idempotent: no unscored lines left"
            once = FilePageStore(Path(d))
            await once.open()
            assert any(ln.imp is not None for p in once._pages.values() for ln in p.lines), "imp persisted"
            assert _norm("plan:\nstep one\n step two") == "plan: step one step two", "newlines collapsed"
            # prune drops tombstones (the superseded bike line); wipe keeps only pinned
            await once.prune()
            assert all(not ln.superseded for p in once._pages.values() for ln in p.lines), "prune cleared tombstones"
            wp = await once.wipe_except_pinned()
            assert wp["kept_pinned"] >= 1 and all(ln.pinned for p in once._pages.values() for ln in p.lines), wp

            # a PROJECT-SCOPED directive routes to the global directives.md by kind —
            # it must NOT stamp the project's title/scope_key onto that page, and the
            # heal pass gives directives.md its canonical title.
            with tempfile.TemporaryDirectory() as d2:
                st = FilePageStore(Path(d2))
                st._project_names = {"proj_abc": "Interaction Lab"}
                await st.open()
                await st.add("Always ask before deploying.", kind="directive",
                             scope_kind="project", scope_key="proj_abc", source_ref=SourceRef("user", ""))
                dpage = st._pages[Path(d2) / _DIRECTIVES]
                assert dpage.frontmatter["title"] == "Directives", dpage.frontmatter
                assert "scope_key" not in dpage.frontmatter, "project scope must not leak onto directives.md"
                # multi-word entity title gets an Obsidian alias so [[Interaction Lab]]
                # resolves to the dash-slug file interaction-lab.md.
                e1 = await st.add("Lab note one.", kind="fact", source_ref=SourceRef("user", ""))
                await st.set_labels(e1.id, [], entity_labels=["Interaction Lab"])
                e2 = await st.add("Lab note two.", kind="fact", source_ref=SourceRef("user", ""))
                await st.set_labels(e2.id, [], entity_labels=["Interaction Lab"])
                lab = st._pages[Path(d2) / "topics" / "interaction-lab.md"]
                assert lab.frontmatter.get("aliases") == ["Interaction Lab"], lab.frontmatter
                reopened = FilePageStore(Path(d2))
                await reopened.open()  # heal is idempotent + repairs any prior contamination
                assert reopened._pages[Path(d2) / _DIRECTIVES].frontmatter["title"] == "Directives"
                assert reopened._pages[Path(d2) / "topics" / "interaction-lab.md"].frontmatter["aliases"] == ["Interaction Lab"]
            print("file_store.py self-check OK")

    async def _demo_vec():
        # Hermetic proof of the vector path (embed -> vector_search -> id-map ->
        # rrf fuse -> salience rank -> filter), with a deterministic mock embedder.
        import numpy as np

        def _v(text: str) -> np.ndarray:
            v = np.zeros(64, dtype=np.float32)
            for tok in re.findall(r"\w+", text.lower()):
                v[hash(tok) % 64] += 1.0
            n = float(np.linalg.norm(v))
            return v / n if n else v

        class _Store:
            def __init__(self):
                self.items: dict[int, tuple] = {}
                self.nid = 0

            async def get_indexed_hashes(self, source):
                return {sid: (rid, str(hash(c))) for rid, (s, sid, _vec, _m, c) in self.items.items() if s == source}

            async def get_by_id(self, rid):
                it = self.items.get(rid)
                return type("I", (), {"metadata": it[3]}) if it else None

            async def vector_search(self, emb_bytes, sources=None, limit=10):
                q = np.frombuffer(emb_bytes, dtype=np.float32)
                out = [(rid, float(np.dot(q, vec))) for rid, (s, _sid, vec, _m, _c) in self.items.items()
                       if not sources or s in sources]
                out.sort(key=lambda t: t[1], reverse=True)
                return out[:limit]

        class _Emb:
            @staticmethod
            async def embed_one(t):
                return _v(t)

        class _Index:
            def __init__(self):
                self.embedder = _Emb()
                self.store = _Store()

            async def upsert(self, source, source_id, title, content, metadata):
                st = self.store
                for rid, (s, sid, *_r) in list(st.items.items()):
                    if s == source and sid == source_id:
                        del st.items[rid]
                st.nid += 1
                st.items[st.nid] = (source, source_id, _v(f"{title}\n{content}"), metadata, content)

            async def delete(self, source, source_id):
                st = self.store
                for rid, (s, sid, *_r) in list(st.items.items()):
                    if s == source and sid == source_id:
                        del st.items[rid]

        with tempfile.TemporaryDirectory() as d:
            store = FilePageStore(Path(d), search_index=_Index())
            await store.open()
            await store.add("Tim commutes on a gravel bicycle every day.", kind="fact", source_ref=SourceRef("user", ""))
            await store.add("The capital of France is Paris.", kind="fact", source_ref=SourceRef("user", ""))
            await store.add("Tim's wife is named Lena.", kind="fact", source_ref=SourceRef("user", ""))
            # query shares tokens with the bicycle line via the mock vector + lexical legs
            await asyncio.sleep(0)  # let fire-and-forget _index upserts run
            hits = await store.search("which bicycle does Tim commute on", limit=2, scopes=None)
            assert hits and "bicycle" in hits[0].text.lower(), hits
            # vectors exist + get cleaned on delete
            assert len(await store._search_index.store.get_indexed_hashes(_MEMORY_LINE_SOURCE)) == 3
            await store.delete(hits[0].id)
            await asyncio.sleep(0)  # let fire-and-forget _unindex run
            assert len(await store._search_index.store.get_indexed_hashes(_MEMORY_LINE_SOURCE)) == 2
            print("file_store.py vector-path self-check OK")

    asyncio.run(_demo())
    asyncio.run(_demo_vec())
