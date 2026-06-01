"""Unit tests for LensMembership — the computed-projection engine (a cache, not edges).

Tmp in-memory SQLite ONLY — never ~/.ntrp/memory.db, never the network. The
cheap/strong LLMs are the shared FakeCompletionClient: each test queues the exact
MembershipBatch the model would return and asserts `.calls` for the cost ceiling.
The embedder is the shared FakeEmbedder.

A lens is a VIEW; membership is a COMPUTED PROJECTION cached in
`lens_membership_cache`, NEVER a graph edge. The load-bearing invariants:
  §0 ban    — membership flips with the LLM verdict ONLY; identical embeddings +
              opposite verdicts are both honored; a degraded embedder still decides.
  cache     — `in` verdicts land in the cache; `out`/`defer` cache no member.
  §3.6      — candidate-K bound: judge calls <= touched lenses, never O(corpus).
  §4.2      — `defer` escalates to the strong model; still-`defer` stays a non-member.
  §7        — coverage is a pure COUNT ratio, advisory only, mutates nothing.
"""

import uuid

import aiosqlite
import pytest
import pytest_asyncio

from ntrp.memory.models import (
    LensProvenance,
    LensRow,
    MembershipDecision,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
)
from ntrp.memory.pipeline.membership import LensMembership
from ntrp.memory.pipeline.prompts_reconcile import MembershipBatch, MembershipVote
from ntrp.memory.store import MemoryStore
from tests.conftest import FakeCompletionClient, FakeEmbedder

USER = Scope(kind=ScopeKind.USER)


# --- fixtures / builders ---------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await s.init_schema()
    yield s
    await conn.close()


_slug_n = 0


def _lens_slug() -> str:
    global _slug_n
    _slug_n += 1
    return f"lens-{_slug_n}"


def _vote(i, decision):
    return MembershipVote(item_index=i, decision=decision, rationale="")


def _batch(*pairs):
    return MembershipBatch(votes=[_vote(i, d) for i, d in pairs])


async def _claim(store, content, **kw):
    c = MemoryItem(
        id=uuid.uuid4().hex,
        content=content,
        canonical_subject=kw.pop("canonical_subject", "Tim"),
        scope=USER,
        provenance=kw.pop("provenance", Provenance.RECORDED),
        **kw,
    )
    return await store.create_item(c)


async def _lens(store, *, name, criterion, page=None):
    le = LensRow(
        id=_lens_slug(),
        name=name,
        criterion=criterion,
        scope=USER,
        provenance=LensProvenance.USER_AUTHORED,
    )
    await store.create_lens_row(le)
    if page is not None:
        await store.update_lens(le.id, page=page)
    return await store.get_lens(le.id)


def _membership(store, cheap, strong=None, embed=None):
    return LensMembership(
        store,
        cheap,
        strong or FakeCompletionClient(),
        embed or FakeEmbedder(),
        cheap_model="cheap",
        strong_model="strong",
    )


async def _members(store, lens_id):
    """The lens's `in`-cache members (the projection), not a graph edge set."""
    cached = await store.get_membership(lens_id, decision=MembershipDecision.IN)
    return {v.claim_id for v in cached}


# --- score + cache: members only on `in` -----------------------------


async def test_score_caches_member_only_on_in(store):
    lens = await _lens(store, name="Health", criterion="claims about the user's health")
    c_in = await _claim(store, "user runs 5k every morning")
    c_out = await _claim(store, "user uses a macbook")
    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (1, "out"))])

    m = _membership(store, cheap)
    verdicts = await m._judge_and_cache([c_in, c_out], lens)

    assert {v.claim_id: v.decision for v in verdicts} == {
        c_in.id: MembershipDecision.IN,
        c_out.id: MembershipDecision.OUT,
    }
    assert await _members(store, lens.id) == {c_in.id}  # only `in` is a member


async def test_out_and_defer_cache_no_member(store):
    lens = await _lens(store, name="Work", criterion="claims about the user's job")
    c0 = await _claim(store, "alpha")
    c1 = await _claim(store, "beta")
    # cheap defers c1; strong (escalation) also defers -> stays a non-member.
    cheap = FakeCompletionClient(queue=[_batch((0, "out"), (1, "defer"))])
    strong = FakeCompletionClient(queue=[_batch((0, "defer"))])

    m = _membership(store, cheap, strong)
    verdicts = await m._judge_and_cache([c0, c1], lens)

    decisions = {v.claim_id: v.decision for v in verdicts}
    assert decisions[c1.id] is MembershipDecision.DEFER
    assert await _members(store, lens.id) == set()  # no member cached


# --- escalation: defer -> strong -------------------------------------


async def test_defer_escalates_to_strong_and_in_becomes_member(store):
    lens = await _lens(store, name="Travel", criterion="claims about user travel")
    c = await _claim(store, "user flew to Tokyo last week")
    cheap = FakeCompletionClient(queue=[_batch((0, "defer"))])
    strong = FakeCompletionClient(queue=[_batch((0, "in"))])

    m = _membership(store, cheap, strong)
    verdicts = await m._judge_and_cache([c], lens)

    assert verdicts[0].decision is MembershipDecision.IN
    assert len(strong.calls) == 1  # exactly one escalation call for the one defer
    assert await _members(store, lens.id) == {c.id}


async def test_only_defers_escalate_not_every_item(store):
    lens = await _lens(store, name="Food", criterion="claims about user food prefs")
    cs = [await _claim(store, f"food fact {i}") for i in range(4)]
    cheap = FakeCompletionClient(
        queue=[_batch((0, "in"), (1, "out"), (2, "defer"), (3, "out"))]
    )
    strong = FakeCompletionClient(queue=[_batch((0, "out"))])

    m = _membership(store, cheap, strong)
    await m._judge_and_cache(cs, lens)

    assert len(strong.calls) == 1  # one defer -> one strong call, not four


# --- §3.6 candidate-K bound: no O(corpus) blowup ---------------------


async def test_incremental_judge_calls_bounded_by_touched_lenses(store):
    # Many lenses + many claims, but recall + one batched call per touched lens
    # means cheap judge calls <= number of distinct lenses recalled. The fan-out
    # is bounded by MEMBERSHIP_CANDIDATE_K, never by corpus size.
    lenses = [
        await _lens(store, name=f"topic {i}", criterion=f"claims about subject {i}")
        for i in range(12)
    ]
    claims = [await _claim(store, f"alpha beta gamma fact {i}") for i in range(20)]
    # Default-out for every batch, regardless of count.
    cheap = FakeCompletionClient(default=MembershipBatch())

    m = _membership(store, cheap)
    await m.score_into_active_lenses([c.id for c in claims], USER)

    active = await m._active_lenses(USER)
    assert len(cheap.calls) <= len(active)
    assert len(cheap.calls) <= len(lenses)


async def test_incremental_caches_members_only_for_in_verdicts(store):
    lens_a = await _lens(store, name="A", criterion="claims about apples")
    lens_b = await _lens(store, name="B", criterion="claims about bananas")
    c = await _claim(store, "apples bananas fruit basket")
    # Each recalled lens gets one batched judge call; default says the (single)
    # recall-subset item is `in`. Assert members land only on lenses that voted `in`.
    cheap = FakeCompletionClient(default=_batch((0, "in")))

    m = _membership(store, cheap)
    verdicts = await m.score_into_active_lenses([c.id], USER)

    in_lenses = {v.lens_id for v in verdicts if v.decision is MembershipDecision.IN}
    for lid in in_lenses:
        assert c.id in await _members(store, lid)
    # No member cached on any lens that wasn't recalled/`in`.
    for lid in (lens_a.id, lens_b.id):
        members = await _members(store, lid)
        if lid not in in_lenses:
            assert members == set()


# --- §0 ABSOLUTE BAN guard -------------------------------------------


async def test_identical_embeddings_opposite_verdicts_both_honored(store):
    # Two claims with byte-identical content => identical embeddings & length.
    # The ONLY thing that can flip the verdict is the LLM vote. Opposite votes for
    # identical-embedding claims must both be honored — proving no cosine/length
    # cutoff gates the outcome (§0).
    lens = await _lens(store, name="X", criterion="claims about X")
    c0 = await _claim(store, "identical content here")
    c1 = await _claim(store, "identical content here")
    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (1, "out"))])

    m = _membership(store, cheap)
    verdicts = await m.score([c0, c1], lens)

    by_id = {v.claim_id: v.decision for v in verdicts}
    assert by_id[c0.id] is MembershipDecision.IN
    assert by_id[c1.id] is MembershipDecision.OUT


async def test_degraded_embedder_still_decides_from_fts(store):
    # Embedder raises on every call; recall degrades to FTS, but the LLM still
    # decides over the surfaced candidates — degraded recall, never a degraded
    # decision.
    class _BrokenEmbedder(FakeEmbedder):
        async def embed(self, texts):
            raise RuntimeError("embedder down")

        async def embed_one(self, text):
            raise RuntimeError("embedder down")

    lens = await _lens(store, name="Berlin", criterion="claims about Berlin")
    c = await _claim(store, "user moved to Berlin in spring")
    cheap = FakeCompletionClient(default=_batch((0, "in")))

    m = _membership(store, cheap, embed=_BrokenEmbedder())
    verdicts = await m.score_into_active_lenses([c.id], USER)

    # The decision still happens (a verdict was produced) despite no embeddings.
    assert any(v.decision is MembershipDecision.IN for v in verdicts)
    assert c.id in await _members(store, lens.id)


# --- parse/index robustness ------------------------------------------


async def test_parse_failure_treats_batch_as_all_out(store):
    lens = await _lens(store, name="Y", criterion="claims about Y")
    cs = [await _claim(store, f"y fact {i}") for i in range(3)]
    cheap = FakeCompletionClient(default="not json at all")  # parse fail

    m = _membership(store, cheap)
    verdicts = await m._judge_and_cache(cs, lens)

    assert all(v.decision is MembershipDecision.OUT for v in verdicts)
    assert await _members(store, lens.id) == set()


async def test_out_of_range_and_missing_votes_default_out(store):
    lens = await _lens(store, name="Z", criterion="claims about Z")
    cs = [await _claim(store, f"z fact {i}") for i in range(3)]
    # vote for index 0 (in), an out-of-range index 9 (ignored), nothing for 1/2.
    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (9, "in"))])

    m = _membership(store, cheap)
    verdicts = await m.score(cs, lens)

    by_id = {v.claim_id: v.decision for v in verdicts}
    assert by_id[cs[0].id] is MembershipDecision.IN
    assert by_id[cs[1].id] is MembershipDecision.OUT
    assert by_id[cs[2].id] is MembershipDecision.OUT  # missing -> out


async def test_unknown_decision_string_defaults_out(store):
    lens = await _lens(store, name="W", criterion="claims about W")
    c = await _claim(store, "w fact")
    cheap = FakeCompletionClient(queue=[_batch((0, "maybe"))])  # not in enum

    m = _membership(store, cheap)
    verdicts = await m.score([c], lens)

    assert verdicts[0].decision is MembershipDecision.OUT


# --- Mode 3 lazy backfill --------------------------------------------


async def test_refresh_scans_pool_and_caches_only_in(store):
    lens = await _lens(store, name="Books", criterion="claims about books the user read")
    c0 = await _claim(store, "user read Dune")
    await _claim(store, "user drives a Tesla")  # out — never a member
    c2 = await _claim(store, "user read Neuromancer")
    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (1, "out"), (2, "in"))])

    m = _membership(store, cheap)
    report = await m.refresh_lens_cache(lens.id)

    assert report.scanned == 3
    assert report.members_added == 2
    assert report.capped is False
    members = await _members(store, lens.id)
    assert members == {c0.id, c2.id}


async def test_refresh_batches_the_scan(store):
    # More claims than MEMBERSHIP_BATCH -> multiple cheap calls; cost still
    # bounded (one pass, not per-query). Use default-out so the queued batch shape
    # does not matter.
    from ntrp.constants import MEMBERSHIP_BATCH

    lens = await _lens(store, name="All", criterion="claims about anything")
    for i in range(MEMBERSHIP_BATCH + 5):
        await _claim(store, f"misc fact {i}")
    cheap = FakeCompletionClient(default=MembershipBatch())

    m = _membership(store, cheap)
    report = await m.refresh_lens_cache(lens.id)

    assert report.scanned == MEMBERSHIP_BATCH + 5
    assert len(cheap.calls) == 2  # ceil((B+5)/B) batches


async def test_refresh_caps_oversized_pool(store):
    # Patch the cap small to keep the test cheap, proving capped scan + ranking.
    import ntrp.memory.pipeline.membership as mem_mod

    lens = await _lens(store, name="Big", criterion="claims about big things")
    for i in range(6):
        await _claim(store, f"big fact {i}")
    cheap = FakeCompletionClient(default=MembershipBatch())

    m = _membership(store, cheap)
    orig = mem_mod.BACKFILL_SCAN_CAP
    mem_mod.BACKFILL_SCAN_CAP = 3
    try:
        report = await m.refresh_lens_cache(lens.id)
    finally:
        mem_mod.BACKFILL_SCAN_CAP = orig

    assert report.capped is True
    assert report.scanned == 3  # ranked down to the cap


# --- criterion synthesis: text only, no membership decision ----------


async def test_synthesize_criterion_uses_cheap_llm(store):
    from ntrp.memory.pipeline.prompts_criterion import SynthesizedCriterion

    cheap = FakeCompletionClient(
        queue=[
            SynthesizedCriterion(
                belongs="Claims describing the user's running training and races.",
                profile_shape=["Distance / pace", "Goal races"],
                render_mode="flat",
            )
        ]
    )
    m = _membership(store, cheap)

    crit, mode, _entity_type = await m.synthesize_criterion("Running")

    # The criterion is composed markdown: a Belongs section + a Profile shape section.
    assert "## Belongs" in crit
    assert "running training" in crit
    assert "## Profile shape" in crit
    assert "- Distance / pace" in crit
    assert mode == "flat"
    assert len(cheap.calls) == 1
    assert cheap.calls[0]["model"] == "cheap"


async def test_synthesize_criterion_groups_people_lens(store):
    from ntrp.memory.pipeline.prompts_criterion import SynthesizedCriterion

    cheap = FakeCompletionClient(
        queue=[
            SynthesizedCriterion(
                belongs="A specific individual the user knows, or a relationship between people.",
                profile_shape=["Role", "Relationship to the user"],
                render_mode="grouped_by_subject",
            )
        ]
    )
    m = _membership(store, cheap)

    crit, mode, _entity_type = await m.synthesize_criterion("People")

    assert mode == "grouped_by_subject"
    assert "## Profile shape" in crit


async def test_synthesize_criterion_degrades_to_echo_on_failure(store):
    cheap = FakeCompletionClient(default="not json at all")  # parse fail
    m = _membership(store, cheap)

    crit, mode, _entity_type = await m.synthesize_criterion("Regina Volkov")

    assert "## Belongs" in crit
    assert "Regina Volkov" in crit
    assert mode == "flat"


# --- §7 coverage: advisory only, mutates nothing ---------------------


async def test_coverage_ratio_and_generic_flag(store):
    lens = await _lens(store, name="Gen", criterion="claims about anything at all")
    members = [await _claim(store, f"covered fact {i}") for i in range(3)]
    await _claim(store, "uncovered fact")  # pool=4, members=3 -> ratio 0.75
    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (1, "in"), (2, "in"))])
    m = _membership(store, cheap)
    # Seed the cache with three `in` verdicts (the projection's members).
    await m._judge_and_cache(members, lens)

    before = await _members(store, lens.id)
    adv = await m.coverage(lens.id, USER)
    after = await _members(store, lens.id)

    assert adv.member_count == 3
    assert adv.scope_pool == 4
    assert adv.ratio == pytest.approx(0.75)
    assert adv.generic is True  # >= 0.5
    assert adv.suggestion == "split"
    assert before == after  # advisory only — cache untouched, no member dropped


async def test_coverage_empty_pool_no_divide_by_zero(store):
    lens = await _lens(store, name="Empty", criterion="claims about nothing yet")
    m = _membership(store, FakeCompletionClient())

    adv = await m.coverage(lens.id, USER)

    assert adv.scope_pool == 0
    assert adv.ratio == 0.0
    assert adv.generic is False
    assert adv.suggestion == ""


async def test_coverage_below_band_not_generic(store):
    lens = await _lens(store, name="Narrow", criterion="claims about a narrow topic")
    member = await _claim(store, "the one covered fact")
    for i in range(9):
        await _claim(store, f"other fact {i}")  # pool=10, members=1 -> 0.1
    cheap = FakeCompletionClient(default=_batch((0, "in")))
    m = _membership(store, cheap)
    await m._judge_and_cache([member], lens)

    adv = await m.coverage(lens.id, USER)

    assert adv.ratio == pytest.approx(0.1)
    assert adv.generic is False
