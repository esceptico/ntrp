"""Unit tests for LensProjector + LensWriteBack (LENS_CONTRACTS §3.2, §3.3, §6, §10).

Tmp in-memory SQLite ONLY — never ~/.ntrp/memory.db, never the network. The
cheap/strong LLMs are the shared FakeCompletionClient (queue the exact
MembershipBatch the re-validation judge returns + the PageSynthesis the strong
synth returns; assert `.calls` for the cost ceiling). The embedder is FakeEmbedder.

Load-bearing invariants asserted here:
  §3.2  — page bullets carry a `<!--claim:ID-->` anchor; structured page cached.
  §3.3  — EDIT -> supersede (+ re-add MEMBER_OF); ACCEPT -> feedback + corrob;
          ADD -> WriteSeam (the one prose->claim path); REJECT -> lens-scoped
          negative-example correction, NO edge dropped, claim survives, page hides it.
  §6/§1.1 — re-validate-at-read: after a criterion edit, project returns only still-`in`
          members though the stale member_of edges persist (never removed).
  §9.5  — synthesis failure -> synthesized=False raw anchored list, never blank.
  §0    — membership flips with the LLM verdict only; nothing lexical gates the page.
"""

import uuid

import aiosqlite
import pytest
import pytest_asyncio

from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    Kind,
    LensDetailLevel,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    Status,
)
from ntrp.memory.pipeline.prompts_reconcile import MembershipBatch, MembershipVote
from ntrp.memory.pipeline.prompts_project import PageSynthesis
from ntrp.memory.pipeline.project import LensProjector, mark_lens_dirty, parse_anchors
from ntrp.memory.pipeline.types import PageEditKind, PageEditOp
from ntrp.memory.pipeline.writeback import LensWriteBack, NEGATIVE_EXAMPLES_HEADER
from ntrp.memory.store import MemoryStore
from tests.conftest import FakeCompletionClient, FakeEmbedder

USER = Scope(kind=ScopeKind.USER)


# --- fixtures / builders ---------------------------------------------


@pytest_asyncio.fixture
async def store():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


def _vote(i, decision):
    return MembershipVote(item_index=i, decision=decision, rationale="")


def _batch(*pairs):
    return MembershipBatch(votes=[_vote(i, d) for i, d in pairs])


def _synth(markdown: str) -> PageSynthesis:
    return PageSynthesis(markdown=markdown)


async def _claim(store, content, **kw):
    c = MemoryItem(
        id=uuid.uuid4().hex,
        kind=Kind.CLAIM,
        content=content,
        scope=USER,
        provenance=kw.pop("provenance", Provenance.RECORDED),
        valid_from=kw.pop("valid_from", None),
        **kw,
    )
    return await store.create_item(c)


async def _lens(store, *, name, criterion, page=None, detail=None):
    le = MemoryItem(
        id=uuid.uuid4().hex,
        kind=Kind.LENS,
        content=name,
        scope=USER,
        provenance=Provenance.USER_AUTHORED,
        lens_kind="topic",
        lens_name=name,
        lens_criterion=criterion,
        lens_page=page,
        lens_detail_level=detail,
    )
    return await store.create_item(le)


async def _member(store, lens_id, claim):
    await store.add_edge(
        MemoryEdge(child_id=claim.id, parent_id=lens_id, role=EdgeRole.MEMBER_OF)
    )


async def _member_ids(store, lens_id):
    edges = await store.list_edges(lens_id, direction="to", role=EdgeRole.MEMBER_OF)
    return {e.child_id for e in edges}


def _projector(store, cheap=None, strong=None, embed=None):
    return LensProjector(
        store,
        embed or FakeEmbedder(),
        cheap or FakeCompletionClient(),
        strong or FakeCompletionClient(),
        cheap_model="cheap",
        strong_model="strong",
    )


# A duck-typed WriteSeam: ADD routes through it (§3.3/§4.4). The unit test only needs
# to prove delegation, so a fake records the request and returns a WriteOutcome.
class FakeWriteSeam:
    def __init__(self, store):
        self.store = store
        self.requests = []

    async def admit_and_write(self, request):
        from ntrp.memory.pipeline.write import WriteOutcome

        self.requests.append(request)
        claim = await _claim(self.store, request.content, provenance=request.provenance)
        return WriteOutcome(written=True, item_id=claim.id, reason="Remembered.")


# --- §3.2 projection: anchors + cache + active members ---------------


async def test_project_renders_anchored_bullets_and_caches(store):
    lens = await _lens(store, name="Health", criterion="claims about the user's health")
    c1 = await _claim(store, "user runs 5k every morning")
    c2 = await _claim(store, "user takes vitamin D")
    await _member(store, lens.id, c1)
    await _member(store, lens.id, c2)

    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (1, "in"))])
    synth_md = (
        "# Health\n*Lens · topic · criterion: claims about the user's health*\n\n"
        "## Profile\n"
        f"- Runs 5k every morning. <!--claim:{c1.id}-->\n"
        f"- Takes vitamin D. <!--claim:{c2.id}-->\n"
    )
    strong = FakeCompletionClient(queue=[_synth(synth_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.synthesized is True
    assert set(parse_anchors(page.markdown)) == {c1.id, c2.id}
    assert {b.claim_id for b in page.blocks} == {c1.id, c2.id}
    # structured page is cached into a superseded lens row -> next read is a cache hit.
    refreshed = await _active_lens(store, lens.id)
    assert refreshed.lens_page is not None
    assert c1.id in refreshed.lens_page


async def test_project_cache_hit_costs_zero_synthesis(store):
    c1 = await _claim(store, "user runs 5k")
    page_md = f"# Health\n## Profile\n- Runs 5k. <!--claim:{c1.id}-->\n"
    lens = await _lens(
        store, name="Health", criterion="health", page=page_md, detail=LensDetailLevel.STRUCTURED
    )
    await _member(store, lens.id, c1)

    cheap = FakeCompletionClient()
    strong = FakeCompletionClient()
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.synthesized is True
    assert page.markdown == page_md
    # Cache hit: no re-validation judge call, no synthesis call (§5).
    assert cheap.calls == []
    assert strong.calls == []
    assert {b.claim_id for b in page.blocks} == {c1.id}


# --- §9.5 synthesis failure -> raw anchored list ---------------------


async def test_project_synthesis_failure_degrades_to_raw_list(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k every morning")
    await _member(store, lens.id, c1)

    cheap = FakeCompletionClient(queue=[_batch((0, "in"))])
    # strong returns empty content -> synthesis raises -> raw fallback.
    strong = FakeCompletionClient(queue=[""])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.synthesized is False
    assert page.markdown  # never blank
    assert c1.id in set(parse_anchors(page.markdown))
    assert "user runs 5k every morning" in page.markdown


# --- §6 / §1.1 re-validate-at-read after criterion edit --------------


async def test_revalidate_hides_now_out_member_but_edge_persists(store):
    lens = await _lens(store, name="Health", criterion="health")
    keep = await _claim(store, "user runs 5k every morning")
    drop = await _claim(store, "user drives a tesla")
    await _member(store, lens.id, keep)
    await _member(store, lens.id, drop)

    # criterion narrowed -> re-validation votes the car claim `out`.
    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (1, "out"))])
    synth_md = f"# Health\n## Profile\n- Runs 5k. <!--claim:{keep.id}-->\n"
    strong = FakeCompletionClient(queue=[_synth(synth_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id, refresh=True)

    # only still-`in` renders...
    assert set(parse_anchors(page.markdown)) == {keep.id}
    assert {b.claim_id for b in page.blocks} == {keep.id}
    # ...but the stale member_of edge is NEVER removed (§1.1): both edges persist.
    assert await _member_ids(store, lens.id) == {keep.id, drop.id}
    # the rejected claim itself survives, active.
    assert (await store.get(drop.id)).status is Status.ACTIVE


async def test_empty_members_no_judge_no_synth(store):
    lens = await _lens(store, name="Empty", criterion="nothing")
    cheap = FakeCompletionClient()
    strong = FakeCompletionClient()
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id, refresh=True)

    assert page.blocks == []
    assert cheap.calls == []  # no members -> no re-validation call
    assert strong.calls == []  # no members -> no synthesis call
    assert page.synthesized is True
    assert page.markdown  # header + "no members" placeholder, never blank


# --- §3.3 write-back: ACCEPT ----------------------------------------


async def test_accept_sets_feedback_and_bumps_corroboration(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k", provenance=Provenance.INFERRED)
    await _member(store, lens.id, c1)
    wb = _writeback(store)

    res = await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.ACCEPT, claim_id=c1.id)])

    assert (PageEditKind.ACCEPT, c1.id) in res.applied
    refreshed = await store.get(c1.id)
    assert refreshed.feedback is Feedback.CONFIRMED
    assert refreshed.corroboration == 1


# --- §3.3 write-back: EDIT -> supersede + re-add MEMBER_OF -----------


async def test_edit_supersedes_and_readds_membership(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 3k")
    await _member(store, lens.id, c1)
    wb = _writeback(store)

    res = await wb.apply(
        lens.id,
        [PageEditOp(kind=PageEditKind.EDIT, claim_id=c1.id, new_text="user runs 5k every morning")],
    )

    assert any(k is PageEditKind.EDIT for k, _ in res.applied)
    # predecessor superseded, successor active + a member of the lens.
    assert (await store.get(c1.id)).status is Status.SUPERSEDED
    members = await _member_ids(store, lens.id)
    successor_id = next(k_id for k, k_id in res.applied if k is PageEditKind.EDIT)
    assert successor_id in members
    succ = await store.get(successor_id)
    assert succ.content == "user runs 5k every morning"
    assert succ.status is Status.ACTIVE


# --- §3.3 write-back: REJECT -> correction, no edge dropped ----------


async def test_reject_records_correction_keeps_edge_and_claim(store):
    lens = await _lens(store, name="Health", criterion="health", page="# Health\n")
    c1 = await _claim(store, "user drives a tesla")
    await _member(store, lens.id, c1)
    wb = _writeback(store)

    res = await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.REJECT, claim_id=c1.id)])

    assert (PageEditKind.REJECT, c1.id) in res.applied
    assert res.rederive_triggered is True
    # §1.1: the edge is NOT removed; the claim survives active.
    assert c1.id in await _member_ids(store, lens.id)
    assert (await store.get(c1.id)).status is Status.ACTIVE
    # the negative example is appended to the (superseded -> new active) lens page.
    active_lens = await _active_lens(store, lens.id)
    assert NEGATIVE_EXAMPLES_HEADER in active_lens.lens_page
    assert "user drives a tesla" in active_lens.lens_page


async def test_reject_then_project_hides_claim(store):
    """Full §3.3 loop: REJECT -> correction + dirty -> next project re-validates the
    claim `out` (the membership judge reads the negative example) -> page hides it,
    edge still dangles."""
    lens = await _lens(store, name="Health", criterion="health", page="# Health\n")
    keep = await _claim(store, "user runs 5k every morning")
    rejected = await _claim(store, "user drives a tesla")
    await _member(store, lens.id, keep)
    await _member(store, lens.id, rejected)

    wb = _writeback(store)
    await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.REJECT, claim_id=rejected.id)])

    # the lens row was superseded by the correction; resolve the active head.
    active_lens = await _active_lens(store, lens.id)
    cheap = FakeCompletionClient(queue=[_batch((0, "in"), (1, "out"))])
    synth_md = f"# Health\n## Profile\n- Runs 5k. <!--claim:{keep.id}-->\n"
    strong = FakeCompletionClient(queue=[_synth(synth_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(active_lens.id, refresh=True)

    assert set(parse_anchors(page.markdown)) == {keep.id}
    # edge persists (on the ORIGINAL lens id — supersede mints a new id but never
    # moves an edge, §1.1); claim survives active.
    assert rejected.id in await _member_ids(store, lens.id)
    assert (await store.get(rejected.id)).status is Status.ACTIVE


# --- §3.3 write-back: ADD -> WriteSeam (the one prose->claim path) ---


async def test_add_routes_through_write_seam(store):
    lens = await _lens(store, name="Health", criterion="health")
    seam = FakeWriteSeam(store)
    wb = LensWriteBack(store, seam, membership=None, projector=_projector(store))

    res = await wb.apply(
        lens.id, [PageEditOp(kind=PageEditKind.ADD, new_text="user sleeps 8 hours")]
    )

    assert any(k is PageEditKind.ADD for k, _ in res.applied)
    # the ONLY prose->claim translation went through WriteSeam, nowhere else.
    assert len(seam.requests) == 1
    assert seam.requests[0].content == "user sleeps 8 hours"
    assert seam.requests[0].scope == lens.scope


# --- §3.3 write-back: EDIT_CRITERION -> lens supersede + dirty -------


async def test_edit_criterion_supersedes_lens_and_marks_dirty(store):
    lens = await _lens(store, name="Health", criterion="health")
    wb = _writeback(store)

    res = await wb.apply(
        lens.id,
        [PageEditOp(kind=PageEditKind.EDIT_CRITERION, new_text="cardiovascular health only")],
    )

    assert any(k is PageEditKind.EDIT_CRITERION for k, _ in res.applied)
    assert (await store.get(lens.id)).status is Status.SUPERSEDED
    active_lens = await _active_lens(store, lens.id)
    assert active_lens.lens_criterion == "cardiovascular health only"
    # the successor lens is marked dirty -> next project re-derives (§6).
    proj = _projector(store)
    assert await proj._is_dirty(active_lens.id) is True


# --- §3.3 stale anchor -> rejected, no silent write ------------------


async def test_stale_anchor_op_is_rejected(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k")
    await _member(store, lens.id, c1)
    await store.invalidate(c1.id, status=Status.SUPERSEDED)  # claim moved out from under us
    wb = _writeback(store)

    res = await wb.apply(
        lens.id, [PageEditOp(kind=PageEditKind.EDIT, claim_id=c1.id, new_text="user runs 10k")]
    )

    assert res.applied == []
    assert len(res.rejected) == 1
    op, reason = res.rejected[0]
    assert op.kind is PageEditKind.EDIT
    assert "re-open" in reason


# --- §3.3 apply order + partial failure ------------------------------


async def test_failed_op_lands_in_rejected_rest_apply(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k", provenance=Provenance.INFERRED)
    await _member(store, lens.id, c1)
    wb = _writeback(store)

    res = await wb.apply(
        lens.id,
        [
            PageEditOp(kind=PageEditKind.ACCEPT, claim_id=c1.id),  # applies
            PageEditOp(kind=PageEditKind.EDIT, claim_id="deadbeef", new_text="x"),  # rejected
        ],
    )

    assert (PageEditKind.ACCEPT, c1.id) in res.applied
    assert len(res.rejected) == 1
    assert (await store.get(c1.id)).feedback is Feedback.CONFIRMED


# --- helpers ---------------------------------------------------------


def _writeback(store):
    return LensWriteBack(store, FakeWriteSeam(store), membership=None, projector=_projector(store))


async def _active_lens(store, original_id):
    """Resolve the active head of a lens whose row may have been superseded.

    Walk the supersedes chain forward from the original id. A small read-only helper
    for the tests; the store keeps history walkable (no row is deleted)."""
    current = original_id
    seen = set()
    while current not in seen:
        seen.add(current)
        item = await store.get(current)
        if item is not None and item.status is Status.ACTIVE:
            return item
        # find a successor: an edge child --SUPERSEDES--> current
        succ = await store.list_edges(current, direction="to", role=EdgeRole.SUPERSEDES)
        if not succ:
            return item
        current = succ[0].child_id
    return await store.get(original_id)
