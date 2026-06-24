"""File-native synthesis: write clean cited prose into each page's COMPILED zone.

Walks the live FilePageStore pages, turns each page's active timeline records into
Records, routes to the EXISTING prompts (prompts_synthesis: PROFILE/DOSSIER/
ACTIVE_WORK — the same ones that produced the old prose), validates that every
(record:XXXXXXXX) cite resolves to a real record, and writes the prose into
page.prose then persists. Stale-gated: a pass only re-synthesizes pages whose
prose is empty or older than their newest record. Reuses prompts_synthesis verbatim;
no new prompts, no dependency on the legacy ArtifactMemoryStore.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ntrp.logging import get_logger
from ntrp.memory import prompts_synthesis as ps
from ntrp.memory.file_store import _slug, load_conventions
from ntrp.memory.models import Record, now_iso
from ntrp.memory.project_names import resolve_project_title

_logger = get_logger(__name__)

ACTIVE_WORK_RECENT_DAYS = 7
DAILY_RECENT_DAYS = 7  # regenerate daily logs for this trailing window; older days freeze
DAILY_MIN_RECORDS = 2  # a day with fewer meaningful records gets no page
PROFILE_RECORD_CAP = 80
REGRESSION_FLOOR = 0.60  # reject a re-synthesis that drops below 60% of prior size/cites (anti-collapse)
_SKIP_DIRS = {"changelog", "context", "facts", ".index", ".maintenance", "sources", "insights"}
_SKIP_NAMES = {"directives.md", "references.md", "lessons.md", "needs-triage.md", "inbox.md", "index.md", "README.md", "AGENTS.md", "health.md"}
_WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")


def _flat(labels_by_id: dict[str, list], ids) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    wanted = {getattr(r, "id", r) for r in ids}
    for rid, entries in labels_by_id.items():
        if rid in wanted:
            out[rid] = [e["label"] if isinstance(e, dict) else e for e in entries]
    return out


def _strip_unknown_wikilinks(text: str, known_titles: list[str]) -> str:
    known = {t.strip().lower() for t in known_titles}

    def repl(m: re.Match) -> str:
        title = m.group(1).strip()
        display = (m.group(2) or title).strip()
        return m.group(0) if title.lower() in known else display

    return _WIKILINK_RE.sub(repl, text)


async def _complete(llm, model, system, user, effort) -> str | None:
    try:
        resp = await llm.completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model,
            reasoning_effort=effort,
            langfuse_name="memory.synthesize",
        )
    except Exception:
        _logger.warning("memory synthesis LLM call failed", exc_info=True)
        return None
    content = resp.choices[0].message.content if resp.choices else None
    return content.strip() if content and content.strip() else None


def _pre(system: str, conventions: str) -> str:
    """Prepend the shared operating manual as a static cacheable block ahead of the
    tuned task system prompt (additive — the task prompt is never altered)."""
    return f"<operating_manual>\n{conventions}\n</operating_manual>\n\n{system}" if conventions else system


def _provenance_ok(text: str, allowed: set[str]) -> bool:
    return ps.cited_ids(text).issubset({a[:8].lower() for a in allowed})


def _regression_ok(page, candidate: str) -> bool:
    """GEPA-style anti-collapse guard: reject a re-synthesis that drops token or
    citation count below REGRESSION_FLOOR of the prior (keep the prior prose).
    First synthesis (no baseline) always passes."""
    prior_tokens = int(page.frontmatter.get("prose_tokens") or 0)
    prior_cites = int(page.frontmatter.get("prose_cites") or 0)
    if prior_tokens == 0 and prior_cites == 0:
        return True
    new_tokens = len(candidate.split())
    new_cites = len(ps.cited_ids(candidate))
    tokens_ok = prior_tokens == 0 or new_tokens >= prior_tokens * REGRESSION_FLOOR
    cites_ok = prior_cites == 0 or new_cites >= prior_cites * REGRESSION_FLOOR
    if not (tokens_ok and cites_ok):
        _logger.warning(
            "synthesis regression rejected — keeping prior prose",
            new_tokens=new_tokens, prior_tokens=prior_tokens, new_cites=new_cites, prior_cites=prior_cites,
        )
    return tokens_ok and cites_ok


def _page_kind(root: Path, path: Path) -> str | None:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    if rel.parts and rel.parts[0] in _SKIP_DIRS:
        return None
    if rel.name in _SKIP_NAMES:
        return None
    if rel.name == "me.md":
        return "profile"
    if rel.name == "active-work.md":
        return "active_work"
    if rel.parts and rel.parts[0] == "daily":
        return "daily"
    if rel.parts and rel.parts[0] == "observations":
        return "overview"
    if rel.parts and rel.parts[0] in ("topics", "entities", "projects"):
        return "dossier"
    return None


def _stale(page) -> bool:
    if not page.prose:
        return True
    newest = max((ln.date for ln in page.active_lines()), default="")
    return (newest or "") > str(page.frontmatter.get("prose_synced", ""))


def _known_titles(store) -> list[str]:
    out: list[str] = []
    for path, page in store._pages.items():
        if _page_kind(store._root, path) == "dossier":
            title = page.frontmatter.get("title")
            if title:
                out.append(str(title))
    return out


def _rename_project_pages(store) -> None:
    """Retitle + rename a project page filed under its opaque scope-id to its human
    name, within the unified topics/ folder. A project page is any topics/ page with a
    scope_key. Idempotent (once renamed, slug == filename)."""
    names = getattr(store, "_project_names", {}) or {}
    if not names:
        return
    root = store._root
    for path in list(store._pages.keys()):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if not rel.parts or rel.parts[0] != "topics":
            continue
        page = store._pages[path]
        key = page.frontmatter.get("scope_key")
        human = names.get(str(key)) if key else None
        if not human:
            continue
        page.frontmatter["title"] = human
        new_path = root / "topics" / f"{_slug(human)}.md"
        if new_path == path:
            store._persist(path)
            continue
        if new_path in store._pages or new_path.exists():
            store._persist(path)  # slug collision: keep filename, fix title only
            continue
        store._pages[new_path] = page
        del store._pages[path]
        for ln in page.lines:
            store._loc[ln.id] = new_path
        store._persist(new_path)
        try:
            path.unlink()
        except OSError:
            pass


# -- per-page synthesizers -----------------------------------------------------


async def _synth_profile(store, labels, llm, model, effort, conventions: str = "") -> str | None:
    rows = await store.list(limit=None, scopes=None)
    directives = [r for r in rows if r.kind == "directive"]
    facts = [
        r for r in rows
        if r.kind == "fact"
        and (r.scope_kind or "").lower() in ("user", "global", "")
        and not (r.source_ref and r.source_ref.kind == "dreamer")
    ]
    pinned = [r for r in rows if r.pinned and r.kind != "source"]
    seen: set[str] = set()
    sel: list[Record] = []
    for r in [*directives, *facts, *pinned]:
        if r.id not in seen:
            seen.add(r.id)
            sel.append(r)
    if not sel:
        return None
    sel.sort(key=lambda r: (r.pinned, r.last_confirmed_at), reverse=True)
    sel = sel[:PROFILE_RECORD_CAP]
    known = _known_titles(store)
    user = ps.profile_user_message(sel, _flat(labels, sel), known_subjects=known)
    out = await _complete(llm, model, _pre(ps.PROFILE_SYSTEM, conventions), user, effort)
    if not out or not _provenance_ok(out, {r.id for r in sel}):
        return None
    return _strip_unknown_wikilinks(out, known).rstrip()


async def _synth_dossier(store, path, labels, llm, model, effort, conventions: str = "") -> str | None:
    page = store._pages[path]
    rows = [store._to_record(ln, path) for ln in page.active_lines() if ln.src != "dreamer"]
    if page.frontmatter.get("scope_key"):  # a project page (now in topics/) — resolve human name
        title = resolve_project_title(page, getattr(store, "_project_names", {}) or {})
    else:
        title = str(page.frontmatter.get("title") or path.stem)
    ordered = sorted(rows, key=lambda r: r.last_confirmed_at, reverse=True)
    user = ps.dossier_user_message(title, ordered, _known_titles(store), _flat(labels, ordered))
    out = await _complete(llm, model, _pre(ps.DOSSIER_SYSTEM, conventions), user, effort)
    if not out or out.strip() == ps.INSUFFICIENT_DOSSIER:
        return None
    if not _provenance_ok(out, {r.id for r in ordered}):
        return None
    return out.rstrip()


async def _synth_active_work(store, labels, llm, model, effort, conventions: str = "") -> str | None:
    rows = await store.list(limit=None, scopes=None)
    cutoff = (datetime.now(UTC) - timedelta(days=ACTIVE_WORK_RECENT_DAYS)).isoformat()
    recent = [
        r for r in rows
        if r.kind != "source"
        and (r.last_confirmed_at or "") >= cutoff
        and not (r.source_ref and r.source_ref.kind == "dreamer")
    ]
    project = [r for r in rows if (r.scope_kind or "").lower() == "project"]
    if not recent and not project:
        return None
    user = ps.active_work_user_message(recent, project, _flat(labels, [*recent, *project]))
    out = await _complete(llm, model, _pre(ps.ACTIVE_WORK_SYSTEM, conventions), user, effort)
    if not out:
        return None
    if out.strip() == ps.NO_ACTIVE_WORK:
        return out  # sentinel written as-is (provenance bypassed)
    if not _provenance_ok(out, {r.id for r in [*recent, *project]}):
        return None
    return out.rstrip()


async def _synth_overview(store, path, labels, llm, model, effort, conventions: str = "") -> str | None:
    """Integration-source overview (the dex-style SOP): synthesize the raw
    observation stream on observations/<source>.md into a 'what's here / patterns'
    map, written into the page's prose zone above the timeline."""
    page = store._pages[path]
    rows = [store._to_record(ln, path) for ln in page.active_lines()]
    if not rows:
        return None
    ordered = sorted(rows, key=lambda r: r.last_confirmed_at, reverse=True)
    user = ps.overview_user_message(path.stem, ordered, _flat(labels, ordered))
    out = await _complete(llm, model, _pre(ps.OVERVIEW_SYSTEM, conventions), user, effort)
    if not out or out.strip() == ps.NO_OVERVIEW:
        return None
    if not _provenance_ok(out, {r.id for r in ordered}):
        return None
    return out.rstrip()


_DAILY_SKIP_KINDS = {"observation", "changelog"}


def _daily_records(store, day: str) -> list:
    """Meaningful records that entered memory on `day` (by append date), gathered
    across the whole store. Integration observations and housekeeping are excluded
    so the daily log reads as what the USER did, not inbox noise."""
    out: list = []
    for path, page in store._pages.items():
        if _page_kind(store._root, path) == "daily":
            continue
        for ln in page.active_lines():
            if ln.date == day and ln.kind not in _DAILY_SKIP_KINDS:
                out.append(store._to_record(ln, path))
    return out


async def _synth_daily(store, path, labels, llm, model, effort, conventions: str = "") -> str | None:
    day = path.stem
    recs = _daily_records(store, day)
    if len(recs) < DAILY_MIN_RECORDS:
        return None
    recs.sort(key=lambda r: r.last_confirmed_at)
    user = ps.daily_user_message(day, recs, _flat(labels, recs))
    out = await _complete(llm, model, _pre(ps.DAILY_SYSTEM, conventions), user, effort)
    if not out or out.strip() == ps.NO_DAILY:
        return None
    if not _provenance_ok(out, {r.id for r in recs}):
        return None
    return out.rstrip()


# -- driver --------------------------------------------------------------------


async def run_synthesis(store, llm, model: str, *, reasoning_effort: str | None = None) -> str:
    if llm is None or not model:
        return "synthesis skipped: no memory model configured"
    conventions = load_conventions()  # shared operating manual, prepended to every pass (additive)
    _rename_project_pages(store)  # fix opaque names + titles BEFORE synth so cites/links use the human name
    # active-work.md is a cross-cutting thread with no timeline of its own — ensure
    # the page exists so the loop synthesizes it (the synthesizer pulls from across
    # the store, not from this page's lines).
    store._ensure_page(store._root / "active-work.md", title="Active work")
    # Daily logs: a dated page per recent day that has meaningful (non-observation)
    # records. Pages in the trailing window are regenerated each run (a day can gain
    # records); days that scroll past the window keep their last prose and freeze.
    today = datetime.now(UTC).date()
    recent_days = {(today - timedelta(days=i)).isoformat() for i in range(DAILY_RECENT_DAYS)}
    for d in recent_days:
        if len(_daily_records(store, d)) >= DAILY_MIN_RECORDS:
            store._ensure_page(store._root / "daily" / f"{d}.md", title=d)
    all_records = await store.list(limit=None, scopes=None)
    labels = await store.labels_for([r.id for r in all_records], include_kind=True)
    known_titles = _known_titles(store)  # links survive only to real topic pages (no dangling [[X]] in Obsidian)
    done: list[str] = []
    for path in list(store._pages.keys()):
        kind = _page_kind(store._root, path)
        if kind is None:
            continue
        page = store._pages[path]
        # active_work and in-window daily pages have no timeline of their own, so
        # _stale (which reads local lines) can't judge them — force re-synth so they
        # track the store's current state. Past-window daily pages fall through to
        # _stale and freeze once written.
        force = kind == "active_work" or (kind == "daily" and path.stem in recent_days)
        if not force and not _stale(page):
            continue
        if kind == "profile":
            prose = await _synth_profile(store, labels, llm, model, reasoning_effort, conventions)
        elif kind == "active_work":
            prose = await _synth_active_work(store, labels, llm, model, reasoning_effort, conventions)
        elif kind == "daily":
            prose = await _synth_daily(store, path, labels, llm, model, reasoning_effort, conventions)
        elif kind == "overview":
            prose = await _synth_overview(store, path, labels, llm, model, reasoning_effort, conventions)
        else:
            prose = await _synth_dossier(store, path, labels, llm, model, reasoning_effort, conventions)
        if prose is None:
            continue
        # Strip wikilinks to subjects that have no page (parked sub-threshold entities)
        # so the vault has no dangling [[X]] links in Obsidian — every pass, not just profile.
        prose = _strip_unknown_wikilinks(prose, known_titles)
        # Sentinels are deliberate short strings — exempt from the regression guard.
        if prose not in (ps.NO_ACTIVE_WORK, ps.INSUFFICIENT_DOSSIER, ps.NO_OVERVIEW) and not _regression_ok(page, prose):
            continue
        page.prose = prose
        page.frontmatter["prose_synced"] = now_iso()[:10]
        page.frontmatter["prose_tokens"] = len(prose.split())
        page.frontmatter["prose_cites"] = len(ps.cited_ids(prose))
        store._persist(path)
        done.append(path.stem)
    msg = f"synthesized {len(done)} pages ({', '.join(done) or 'none'})"
    _logger.info(msg)
    return msg


if __name__ == "__main__":
    import asyncio
    import tempfile

    from ntrp.memory.file_store import FilePageStore
    from ntrp.memory.models import SourceRef

    class _FakeLLM:
        def __init__(self) -> None:
            self.mode = "echo"
            self.calls = 0

        async def completion(self, *, messages, model, reasoning_effort=None, langfuse_name=None):
            self.calls += 1
            user = messages[-1]["content"]
            if self.mode == "insufficient":
                content = ps.INSUFFICIENT_DOSSIER
            elif self.mode == "fabricate":
                content = "Bogus claim. (record:deadbeef)"
            else:
                m = re.search(r"\[([0-9a-f]{6,})\]", user)
                cid = m.group(1) if m else "00000000"
                content = f"Synthesized prose summary. (record:{cid})"
            msg = type("M", (), {"content": content})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    async def _demo():
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store = FilePageStore(root)  # no name map yet -> simulates legacy opaque filing
            await store.open()
            # Two records promote "Bicycles" to its own page (one would just park on me.md).
            r = await store.add("Tim rides a gravel bike daily.", kind="fact", source_ref=SourceRef("user", ""))
            await store.set_labels(r.id, [], entity_labels=["Bicycles"])
            rb = await store.add("Tim's bike has 700c wheels.", kind="fact", source_ref=SourceRef("user", ""))
            await store.set_labels(rb.id, [], entity_labels=["Bicycles"])
            bike_path = root / "topics" / "bicycles.md"
            assert bike_path in store._pages, "two records should promote the entity to its own page"

            fake = _FakeLLM()
            await run_synthesis(store, fake, "m")
            page = store._pages[bike_path]
            ids = {ln.id for ln in page.active_lines()}
            assert page.prose and any(f"(record:{i}" in page.prose for i in ids), page.prose
            assert len(page.active_lines()) == 2, "timeline must survive synthesis"
            assert "<!-- timeline" in bike_path.read_text(encoding="utf-8"), "sentinel + timeline persist"
            # active-work.md is a cross-cutting thread (no own timeline) — created + synthesized from the store
            aw = root / "active-work.md"
            assert aw in store._pages and store._pages[aw].prose, "active-work.md synthesized from across the store"

            # stale gate: unchanged dossiers are skipped; active-work and today's
            # daily log always refresh (both are timeline-less, window-current pages).
            before = fake.calls
            await run_synthesis(store, fake, "m")
            assert fake.calls == before + 2, "only active-work + today's daily re-synthesize; stale dossiers are skipped"

            # provenance rejection: a new page whose synthesis cites a fake id is rejected
            r2 = await store.add("Cats are great.", kind="fact", source_ref=SourceRef("user", ""))
            await store.set_labels(r2.id, [], entity_labels=["Cats"])
            r2b = await store.add("Cats purr when content.", kind="fact", source_ref=SourceRef("user", ""))
            await store.set_labels(r2b.id, [], entity_labels=["Cats"])
            fake.mode = "fabricate"
            await run_synthesis(store, fake, "m")
            assert store._pages[root / "topics" / "cats.md"].prose == "", "fabricated cite must be rejected"

            # integration overview: an observation source gets a synthesized SOP above its raw stream
            fake.mode = "echo"
            for i in range(3):
                await store.add(f"Email about topic {i}.", kind="observation", source_ref=SourceRef("gmail", f"g{i}"))
            gmail_obs = root / "observations" / "gmail.md"
            assert gmail_obs in store._pages, "observation source page exists"
            await run_synthesis(store, fake, "m")
            assert store._pages[gmail_obs].prose, "observation source got a synthesized overview"
            assert len(store._pages[gmail_obs].active_lines()) == 3, "raw observation stream survives under the overview"

            # daily log: a dated, prose-only page aggregating the day's MEANINGFUL
            # records (facts), with integration observations filtered out.
            today = datetime.now(UTC).date().isoformat()
            day_recs = _daily_records(store, today)
            assert all(r.kind not in _DAILY_SKIP_KINDS for r in day_recs), "observations/changelog excluded from daily"
            assert any(r.kind == "fact" for r in day_recs), "facts feed the daily log"
            daily_path = root / "daily" / f"{today}.md"
            assert daily_path in store._pages, "daily page created for today"
            dp = store._pages[daily_path]
            assert dp.prose and "(record:" in dp.prose, "daily page synthesized with cites"
            assert not dp.active_lines(), "daily page is a prose-only projection (no own records)"

            # project rename: opaque-id page -> human name (add files under slug of scope_key)
            await store.add("ntrp is the OS.", kind="fact", scope_kind="project", scope_key="proj_x", source_ref=SourceRef("user", ""))
            opaque = root / "topics" / "proj-x.md"  # _slug("proj_x") == "proj-x"
            assert opaque.exists(), f"project page filed under slug of scope_key; got {list((root/'topics').iterdir())}"
            store._project_names = {"proj_x": "ntrp"}  # name map now available (e.g. from sessions.db)
            _rename_project_pages(store)
            assert (root / "topics" / "ntrp.md").exists(), "project renamed to human name"
            assert not opaque.exists(), "opaque project page removed"
            _rename_project_pages(store)  # idempotent
            assert (root / "topics" / "ntrp.md").exists()
            print("synthesize.py self-check OK")

    asyncio.run(_demo())
