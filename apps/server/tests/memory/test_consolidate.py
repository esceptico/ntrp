"""Unit tests for ConsolidateLint (pipeline §8).

Tmp in-memory SQLite DBs ONLY — never ~/.ntrp/memory.db. The cheap/strong LLMs
are faked: each test scripts the exact LintOps the model would return, so we test
the processor's apply/durability/guard logic deterministically, not the model.
"""


import aiosqlite
import pytest
import pytest_asyncio

from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    Status,
)
from ntrp.memory.pipeline.consolidate import ConsolidateConfig, ConsolidateLint
from ntrp.memory.pipeline.prompts_consolidate import (
    DropOrphanOp,
    InvalidateOp,
    LintOps,
    MergeOp,
)
from ntrp.memory.store import MemoryStore

USER = Scope(kind=ScopeKind.USER)


# --- fakes ------------------------------------------------------------


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeLLM:
    """Returns a scripted LintOps for each call; raises if it runs dry."""

    def __init__(self, scripted: list[LintOps] | None = None):
        self._queue = list(scripted or [])
        self.calls = 0

    async def completion(self, **kwargs):
        self.calls += 1
        if self._queue:
            ops = self._queue.pop(0)
        else:
            ops = LintOps()
        return _Resp(ops.model_dump_json())

    async def close(self):
        pass


# --- fixtures ---------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await s.init_schema()
    yield s
    await conn.close()


def _claim(content, *, provenance=Provenance.RECORDED, feedback=Feedback.NONE,
           source_refs=None, corroboration=0):
    import uuid
    return MemoryItem(
        id=str(uuid.uuid4()),
        content=content,
        canonical_subject="Tim",
        scope=USER,
        provenance=provenance,
        feedback=feedback,
        corroboration=corroboration,
        source_refs=source_refs or [],
    )


def _lint(store, cheap, strong=None, **cfg):
    config = ConsolidateConfig(consolidation_interval=cfg.pop("interval", 30), **cfg)
    return ConsolidateLint(
        store, cheap, strong or FakeLLM(), model="fake-model", config=config
    )


# --- tests ------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_collapses_duplicates_and_keeps_best_survivor(store):
    from ntrp.memory.models import SourceRef

    keep = _claim(
        "User lives in Berlin",
        provenance=Provenance.RECORDED,
        corroboration=3,
        source_refs=[SourceRef(kind="chat", ref="a")],
    )
    loser = _claim(
        "User lives in Berlin",
        provenance=Provenance.INFERRED,
        source_refs=[SourceRef(kind="chat", ref="b")],
    )
    await store.create_item(keep)
    await store.create_item(loser)

    cheap = FakeLLM([LintOps(merges=[MergeOp(member_ids=[keep.id, loser.id])])])
    lint = _lint(store, cheap)
    report = await lint.run_once(scope=USER)

    assert report.merged == 1
    active = await store.query(scope=USER, status=Status.ACTIVE)
    assert len(active) == 1
    survivor = active[0]
    # Survivor is a fresh row (supersede minted it) carrying the unioned refs.
    assert survivor.id not in {keep.id, loser.id}
    # The minted id must be a 32-char continuous hex (uuid4().hex), NOT a hyphenated
    # str(uuid4()): the lens anchor regex is hex-only, so a hyphenated id would make
    # the consolidated claim silently vanish from cached lens pages.
    from ntrp.memory.pipeline.project import parse_anchors

    assert "-" not in survivor.id and len(survivor.id) == 32
    assert parse_anchors(f"- text <!--claim:{survivor.id}-->") == [survivor.id]
    assert {r.ref for r in survivor.source_refs} == {"a", "b"}
    # Predecessors preserved as superseded, history walkable.
    assert (await store.get(keep.id)).status is Status.SUPERSEDED
    assert (await store.get(loser.id)).status is Status.SUPERSEDED


@pytest.mark.asyncio
async def test_merge_sums_member_corroboration(store):
    # corroboration = independent evidence links (vision §7). A merge unions the
    # members' source_refs, so the survivor must SUM their corroboration — not inherit
    # only the survivor's count (which silently dropped the losers' trust).
    from ntrp.memory.models import SourceRef

    keep = _claim("User lives in Berlin", corroboration=2,
                  source_refs=[SourceRef(kind="chat", ref="a")])
    loser = _claim("User lives in Berlin", corroboration=2,
                   source_refs=[SourceRef(kind="chat", ref="b")])
    await store.create_item(keep)
    await store.create_item(loser)

    cheap = FakeLLM([LintOps(merges=[MergeOp(member_ids=[keep.id, loser.id])])])
    await _lint(store, cheap).run_once(scope=USER)

    active = await store.query(scope=USER, status=Status.ACTIVE)
    assert len(active) == 1
    assert active[0].corroboration == 4  # 2 + 2, not 2 or 3


@pytest.mark.asyncio
async def test_merge_caps_survivor_provenance_at_inferred(store):
    # USER_AUTHORED but NOT confirmed: it may be merged, but the merge is the
    # LLM's inference, so the survivor's trust is capped at INFERRED. Lint may
    # never raise trust. (A feedback=CONFIRMED claim, by contrast, is never
    # merged — covered by test_merge_never_touches_confirmed_claim.)
    a = _claim("X", provenance=Provenance.USER_AUTHORED)
    b = _claim("X", provenance=Provenance.RECORDED)
    await store.create_item(a)
    await store.create_item(b)
    cheap = FakeLLM([LintOps(merges=[MergeOp(member_ids=[a.id, b.id])])])
    report = await _lint(store, cheap).run_once(scope=USER)
    assert report.merged == 1
    active = await store.query(scope=USER, status=Status.ACTIVE)
    assert len(active) == 1
    assert active[0].provenance is Provenance.INFERRED


@pytest.mark.asyncio
async def test_merge_never_touches_confirmed_claim(store):
    a = _claim("X", feedback=Feedback.CONFIRMED)
    b = _claim("X", provenance=Provenance.INFERRED)
    await store.create_item(a)
    await store.create_item(b)
    cheap = FakeLLM([LintOps(merges=[MergeOp(member_ids=[a.id, b.id])])])
    report = await _lint(store, cheap).run_once(scope=USER)
    assert report.merged == 0
    assert (await store.get(a.id)).status is Status.ACTIVE
    assert (await store.get(b.id)).status is Status.ACTIVE


@pytest.mark.asyncio
async def test_invalidate_stale_archives(store):
    c = _claim("Old fact")
    await store.create_item(c)
    cheap = FakeLLM([LintOps(invalidations=[InvalidateOp(claim_id=c.id, reason="stale")])])
    report = await _lint(store, cheap).run_once(scope=USER)
    assert report.invalidated == 1
    assert (await store.get(c.id)).status is Status.ARCHIVED


@pytest.mark.asyncio
async def test_contradiction_between_high_trust_is_flagged_not_resolved(store):
    a = _claim("User is vegetarian", provenance=Provenance.USER_AUTHORED)
    b = _claim("User eats meat", provenance=Provenance.USER_AUTHORED)
    await store.create_item(a)
    await store.create_item(b)
    cheap = FakeLLM([LintOps(invalidations=[InvalidateOp(claim_id=a.id, contradicted_by=b.id)])])
    report = await _lint(store, cheap).run_once(scope=USER)
    assert report.contradictions_flagged == 1
    assert report.invalidated == 0
    # both stay active; a CONTRADICTS edge links them.
    assert (await store.get(a.id)).status is Status.ACTIVE
    assert (await store.get(b.id)).status is Status.ACTIVE
    edges = await store.list_edges(a.id, direction="to", role=EdgeRole.CONTRADICTS)
    assert len(edges) == 1


@pytest.mark.asyncio
async def test_drop_orphan_requires_no_refs_and_no_edges(store):
    from ntrp.memory.models import SourceRef

    orphan = _claim("Dangling", source_refs=[])
    grounded = _claim("Grounded", source_refs=[SourceRef(kind="chat", ref="x")])
    await store.create_item(orphan)
    await store.create_item(grounded)
    cheap = FakeLLM([
        LintOps(orphans=[DropOrphanOp(claim_id=orphan.id), DropOrphanOp(claim_id=grounded.id)])
    ])
    report = await _lint(store, cheap).run_once(scope=USER)
    # only the truly ref-less, edge-less claim is dropped; the model's overreach
    # on the grounded claim is rejected against the live store.
    assert report.dropped == 1
    assert (await store.get(orphan.id)).status is Status.ARCHIVED
    assert (await store.get(grounded.id)).status is Status.ACTIVE


@pytest.mark.asyncio
async def test_hallucinated_ids_are_dropped_not_dead_ended(store):
    c = _claim("Real claim")
    await store.create_item(c)
    cheap = FakeLLM([LintOps(
        invalidations=[InvalidateOp(claim_id="does-not-exist")],
        orphans=[DropOrphanOp(claim_id="ghost")],
        merges=[MergeOp(member_ids=["nope1", "nope2"])],
    )])
    report = await _lint(store, cheap).run_once(scope=USER)
    assert (report.merged, report.invalidated, report.dropped) == (0, 0, 0)
    assert (await store.get(c.id)).status is Status.ACTIVE


@pytest.mark.asyncio
async def test_watermark_advances_and_skips_unchanged_on_next_sweep(store):
    c = _claim("A fact")
    await store.create_item(c)
    cheap = FakeLLM([LintOps(), LintOps()])  # two empty sweeps allowed
    lint = _lint(store, cheap)

    await lint.run_once(scope=USER)
    calls_after_first = cheap.calls
    assert calls_after_first >= 1  # judged the delta neighborhood

    # Nothing changed since the watermark → second sweep selects no delta and
    # makes zero LLM calls.
    await lint.run_once(scope=USER)
    assert cheap.calls == calls_after_first


@pytest.mark.asyncio
async def test_capped_sweep_does_not_skip_tie_group_straddling_the_cap(store):
    # A group of claims sharing one updated_at can straddle the cap boundary. A
    # strict `>` watermark filter would advance to that timestamp and skip the
    # unprocessed tie-tail FOREVER. The inclusive `>=` filter re-includes the
    # boundary group on the catch-up sweep (idempotent apply makes that safe), so
    # no claim is permanently skipped.
    import uuid

    tie = "2026-06-01T00:00:00.000003+00:00"
    stamps = [
        "2026-06-01T00:00:00.000001+00:00",
        "2026-06-01T00:00:00.000002+00:00",
        tie,
        tie,  # c3 and c4 share the exact boundary timestamp
    ]
    ids = []
    for n, ts in enumerate(stamps):
        c = _claim(f"fact {n}")
        c.id = str(uuid.uuid4())
        c.created_at = ts
        c.updated_at = ts
        await store.create_item(c)
        ids.append(c.id)

    lint = _lint(store, FakeLLM(), max_items_per_sweep=3)

    rows1, capped1, last1 = await lint._select_delta(USER, None)
    assert capped1  # 4 candidates, cap 3 → capped catch-up
    seen = {r.id for r in rows1}

    rows2, _, _ = await lint._select_delta(USER, last1)
    seen |= {r.id for r in rows2}

    # Every claim is selected across the two catch-up sweeps — the tie-tail at the
    # boundary timestamp is not lost.
    assert seen == set(ids)


@pytest.mark.asyncio
async def test_empty_scope_returns_clean_report(store):
    cheap = FakeLLM([])
    report = await _lint(store, cheap).run_once(scope=USER)
    assert (report.merged, report.invalidated, report.dropped) == (0, 0, 0)
    assert cheap.calls == 0


@pytest.mark.asyncio
async def test_degraded_flag_when_fts_unavailable(store):
    store._has_fts = False  # simulate FTS5 unavailable
    c = _claim("Lonely fact")
    await store.create_item(c)
    cheap = FakeLLM([LintOps()])
    report = await _lint(store, cheap).run_once(scope=USER)
    assert report.degraded is True
