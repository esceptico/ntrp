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
from ntrp.memory.models import Kind, Record, SourceRef, now_iso
from ntrp.memory.pages import Line, Page, parse_page, render_page
from ntrp.memory.scorer import salience
from ntrp.search.retrieval import rrf_merge

_logger = get_logger(__name__)

_MEMORY_LINE_SOURCE = "memory_line"  # search.db partition for per-line vectors (own source, never transcripts)
_DIRECTIVES = "directives.md"
_REFERENCES = "references.md"
_ME = "me.md"
_LESSONS = "lessons.md"  # continual-learning playbook (distilled lesson records)
_ENTITIES = "entities"
_OBSERVATIONS = "observations"  # per-source raw integration stream (gmail/slack/calendar), dream-mined
_INSIGHTS = "insights"  # cross-domain DREAM outputs (OKF insights/), kept out of facts/entities
_GENERATED_FILES = {"index.md", "AGENTS.md", "health.md"}  # generated reports, not record pages

_CONVENTIONS = """\
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
- `entities/<slug>.md` — emergent subjects (people/products/projects/topics),
  created only once an entity has ≥2 records (else parked on me.md).
- `projects/<slug>.md` — project-scoped pages.
- `references.md` — source pointers.
- `observations/<source>.md` — raw integration streams (gmail/calendar/slack).
- `insights/<month>.md` — cross-domain dream outputs (provisional, cited).
- `index.md` — this directory's navigational map (generated).
- `.index/` — throwaway search index (rebuildable, never canonical).
"""
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
            if ".index" in path.parts or path.name in _GENERATED_FILES:
                continue  # .index = throwaway; index.md/AGENTS.md = generated, not record pages
            try:
                page = parse_page(path.read_text(encoding="utf-8"))
            except Exception:
                _logger.warning("skip unparseable memory page", path=str(path))
                continue
            self._pages[path] = page
            for line in page.lines:
                self._loc[line.id] = path
        self._backfill_entities()
        stats = await self.reconcile_entities()
        self._write_conventions()  # AGENTS.md (OKF conventions) — static, once
        self._write_index()        # index.md (OKF nav backbone) — deterministic, every open
        self._write_health()       # health.md (self-audit / surfaced gaps) — deterministic
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
        if rel.parts and rel.parts[0] == "projects":
            key = self._pages[path].frontmatter.get("scope_key") or rel.stem
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
            return self._root / "projects" / f"{_slug(self._project_names.get(scope_key, scope_key))}.md"
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
        promoted = sum(1 for _, ln in members if not ln.superseded) >= MEMORY_MIN_ENTITY_RECORDS
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
        reading it understands the format. Static; written once if absent."""
        path = self._root / "AGENTS.md"
        if not path.exists():
            path.write_text(_CONVENTIONS, encoding="utf-8")

    def _write_index(self) -> None:
        """index.md (OKF navigational backbone) — every page grouped by area with a
        one-line description. Deterministic, regenerated each open(); not a record page."""
        groups: dict[str, list[tuple[str, str, str]]] = {}
        for path, page in self._pages.items():
            try:
                rel = path.relative_to(self._root)
            except ValueError:
                continue
            if rel.name in _GENERATED_FILES:
                continue
            area = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            title = str(page.frontmatter.get("title") or rel.stem)
            active = len(page.active_lines())
            prose = (page.prose or "").strip()
            desc = ""
            if prose:
                first = next((ln.strip() for ln in prose.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")
                desc = first[:110]
            desc = desc or f"{active} record{'s' if active != 1 else ''}"
            groups.setdefault(area, []).append((rel.as_posix(), title, desc))
        parts = ["# Memory index", ""]
        for area in sorted(groups):
            parts.append(f"## {area}")
            parts.extend(f"- **{title}** (`{rel}`) — {desc}" for rel, title, desc in sorted(groups[area]))
            parts.append("")
        (self._root / "index.md").write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

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
                    gaps.append(f"- Stale topic: `entities/{path.stem}.md` — no update in {a}d (since {newest}).")
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
            page = Page(frontmatter={"type": page_type, "title": title or path.stem, "updated": now_iso()[:10]})
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
            title = self._project_names.get(scope_key, scope_key) if (scope_kind == "project" and scope_key) else None
        self._append(base, line, title=title)
        # Persist the raw project key so non-slug-safe keys round-trip (the filename
        # is a lossy slug; _scope_for reads scope_key from frontmatter first).
        if scope_kind == "project" and scope_key:
            self._pages[base].frontmatter["scope_key"] = scope_key
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
        self._pages[path].lines = [ln for ln in self._pages[path].lines if ln.id != record_id]
        self._loc.pop(record_id, None)
        self._persist(path)
        self._unindex_line(record_id)

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
            if q_lower and (q_lower in tl or tl in q_lower):
                score += 5.0
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

            bike_page = Path(d) / "entities" / "bicycles.md"
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
            acme = Path(d) / "entities" / "acme.md"
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
            zeta = Path(d) / "entities" / "zeta.md"
            assert zeta.exists()
            await again.delete(q1.id)
            await again.delete(q2.id)
            await again.reconcile_entities()
            assert not zeta.exists(), "empty entity page is reclaimed by the sweep"

            # OBSERVATION routing: a raw integration record streams to observations/<source>.md
            # (never an entity page), stays user-scoped + dream-listable.
            obs = await again.add("Email from Kevin re: PRD-407 review.", kind="observation", source_ref=SourceRef("gmail", "g1"))
            assert (Path(d) / "observations" / "gmail.md").exists(), "observation streams to observations/<source>.md"
            assert not (Path(d) / "entities" / "gmail.md").exists(), "observation never spawns an entity page"
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

            # OKF nav + conventions are generated on open()
            assert (Path(d) / "AGENTS.md").exists(), "AGENTS.md conventions written"
            idx = Path(d) / "index.md"
            assert idx.exists() and "# Memory index" in idx.read_text(encoding="utf-8"), "index.md generated"
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
