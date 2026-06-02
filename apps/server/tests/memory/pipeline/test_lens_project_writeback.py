"""Unit tests for LensProjector + LensWriteBack (the VIEW-layer page surface).

Tmp in-memory SQLite ONLY — never ~/.ntrp/memory.db, never the network. The
cheap/strong LLMs are the shared FakeCompletionClient (queue the exact
MembershipBatch the re-validation judge returns + the PageSynthesis the strong
synth returns; assert `.calls` for the cost ceiling). The embedder is FakeEmbedder.

A lens is a VIEW: membership lives in `lens_membership_cache`, NEVER in a
member_of edge. Load-bearing invariants asserted here:
  projection — page bullets carry a `<!--claim:ID-->` anchor; structured page cached
               into the registry row; cache hit costs zero synthesis.
  re-validate-at-read — after a criterion change, project returns only still-`in`
               members; the cache is just a cache (nothing is destroyed).
  write-back — EDIT -> supersede the claim; ACCEPT -> feedback + corrob; INCLUDE ->
               explicit lens inclusion of an existing claim; REJECT -> lens-scoped
               negative-example correction, claim survives, page hides it next read;
               EDIT_CRITERION -> in-place criterion update + page nulled (dirty).
  §9.5  — synthesis failure -> synthesized=False raw anchored list, never blank.
  §0    — membership flips with the LLM verdict only; nothing lexical gates the page.
"""

import uuid

import aiosqlite
import pytest_asyncio

from ntrp.constants import NEGATIVE_EXAMPLES_HEADER
from ntrp.memory.models import (
    Feedback,
    LensDetailLevel,
    LensProvenance,
    LensRow,
    MembershipDecision,
    MembershipVerdict,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    Status,
)
from ntrp.memory.pipeline.project import LensProjector, parse_anchors
from ntrp.memory.pipeline.prompts_project import PageSynthesis
from ntrp.memory.pipeline.prompts_reconcile import MembershipBatch, MembershipVote
from ntrp.memory.pipeline.types import PageEditKind, PageEditOp
from ntrp.memory.pipeline.writeback import LensWriteBack
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


def _synth(markdown: str) -> PageSynthesis:
    return PageSynthesis(markdown=markdown)


class KeywordJudge:
    """Content-aware membership judge stub: votes `in` for any ITEM whose content
    contains one of `keywords`, else `out`. Parses the numbered ITEMS straight out
    of the prompt so the verdict tracks content, never call/queue order (the judge
    is consulted both by refresh_lens_cache and re-validate-at-read).
    """

    def __init__(self, *keywords: str):
        self.keywords = [k.lower() for k in keywords]
        self.calls: list[dict] = []

    async def completion(self, *, messages, model, response_format=None, **kwargs):
        from tests.conftest import completion_response

        self.calls.append({"messages": messages, "model": model})
        user = messages[-1]["content"]
        votes = []
        for line in user.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("[") and "]" in stripped):
                continue
            try:
                idx = int(stripped[1 : stripped.index("]")])
            except ValueError:
                continue
            body = stripped.lower()
            decision = "in" if any(k in body for k in self.keywords) else "out"
            votes.append(MembershipVote(item_index=idx, decision=decision, rationale=""))
        return completion_response(MembershipBatch(votes=votes).model_dump_json())


async def _claim(store, content, **kw):
    c = MemoryItem(
        id=uuid.uuid4().hex,
        content=content,
        canonical_subject=kw.pop("canonical_subject", "Tim"),
        scope=USER,
        provenance=kw.pop("provenance", Provenance.RECORDED),
        valid_from=kw.pop("valid_from", None),
        **kw,
    )
    return await store.create_item(c)


def test_inject_anchors_ignores_literal_brackets_in_prose():
    # The citation token is `{{n}}`, NOT bare `[n]`. A bracketed integer copied from
    # claim content ("see table [1]") must be left intact — never rewritten into the
    # wrong claim's anchor or silently deleted.
    from ntrp.memory.pipeline.project import _inject_anchors

    m0 = MemoryItem(id="a" * 32, content="x", canonical_subject="Tim", scope=USER, provenance=Provenance.RECORDED)
    m1 = MemoryItem(id="b" * 32, content="y", canonical_subject="Tim", scope=USER, provenance=Provenance.RECORDED)
    md = "See table [1] in the appendix {{0}}. Also relevant {{1}}."

    out, rendered = _inject_anchors(md, [m0, m1])

    assert "See table [1] in the appendix" in out  # literal [1] preserved verbatim
    assert f"<!--claim:{m0.id}-->" in out and f"<!--claim:{m1.id}-->" in out
    assert rendered == {m0.id, m1.id}


async def _lens(
    store,
    *,
    name,
    criterion,
    page=None,
    detail=LensDetailLevel.STRUCTURED,
    render_mode=None,
):
    from ntrp.memory.models import LensRenderMode

    le = LensRow(
        id=_lens_slug(),
        name=name,
        criterion=criterion,
        scope=USER,
        provenance=LensProvenance.USER_AUTHORED,
        detail_level=detail,
        render_mode=render_mode or LensRenderMode.FLAT,
    )
    await store.create_lens_row(le)
    if page is not None:
        await store.update_lens(le.id, page=page)
    return await store.get_lens(le.id)


async def _member(store, lens_id, claim):
    """Seed an `in` membership-cache row — the projection's member set."""
    await store.put_membership([MembershipVerdict(lens_id=lens_id, claim_id=claim.id, decision=MembershipDecision.IN)])


async def _member_ids(store, lens_id):
    cached = await store.get_membership(lens_id, decision=MembershipDecision.IN)
    return {v.claim_id for v in cached}


def _projector(store, cheap=None, strong=None, embed=None):
    return LensProjector(
        store,
        embed or FakeEmbedder(),
        cheap or FakeCompletionClient(),
        strong or FakeCompletionClient(),
        cheap_model="cheap",
        strong_model="strong",
    )


# --- projection: anchors + cache + active members --------------------


async def test_durably_rejected_claim_never_renders_despite_stale_in_row(store):
    # A durable user REJECT must keep a claim OUT regardless of a stale IN cache row
    # (Mode-1 scoring can leave one a refresh-upsert never purges). The read path must
    # enforce the override even when the re-validation judge would vote it back IN.
    lens = await _lens(store, name="Health", criterion="claims about the user's health")
    c1 = await _claim(store, "user runs 5k every morning")
    c2 = await _claim(store, "user takes vitamin D")
    await _member(store, lens.id, c1)
    await _member(store, lens.id, c2)  # stale IN row for the soon-rejected claim
    await store.add_rejection(lens.id, c2.id)

    cheap = KeywordJudge("user")  # would happily keep BOTH (both say "user")
    strong = _IndexCitingSynth()
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id, refresh=True)
    rendered_ids = {b.claim_id for b in page.blocks}
    assert c1.id in rendered_ids
    assert c2.id not in rendered_ids  # rejection enforced at read time


async def test_project_renders_anchored_bullets_and_caches(store):
    lens = await _lens(store, name="Health", criterion="claims about the user's health")
    c1 = await _claim(store, "user runs 5k every morning")
    c2 = await _claim(store, "user takes vitamin D")
    await _member(store, lens.id, c1)
    await _member(store, lens.id, c2)

    # re-validation judge (cheap) keeps both; synthesis (strong) renders the page.
    cheap = KeywordJudge("user")  # both claims mention "user"
    synth_md = (
        "# Health\n*Lens · criterion: claims about the user's health*\n\n"
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
    # structured page is cached into the registry row -> next read is a cache hit.
    refreshed = await store.get_lens(lens.id)
    assert refreshed.page is not None
    assert c1.id in refreshed.page


async def test_flat_lens_sections_render_as_profile_list(store):
    lens = await _lens(store, name="Records", criterion="approved record entries")
    alpha = await _claim(store, "alpha marker belongs in the directory", canonical_subject="User")
    beta = await _claim(store, "beta marker belongs in the directory", canonical_subject="User")
    await _member(store, lens.id, alpha)
    await _member(store, lens.id, beta)

    cheap = KeywordJudge("alpha", "beta")
    synth_md = (
        "# Records\n"
        f"## Record A\n- Alpha marker. <!--claim:{alpha.id}-->\n\n"
        f"## Record B\n- Beta marker. <!--claim:{beta.id}-->\n"
    )
    strong = FakeCompletionClient(queue=[_synth(synth_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.groups is not None
    assert [g.subject for g in page.groups] == ["Record A", "Record B"]
    assert {b.claim_id for b in page.groups[0].blocks} == {alpha.id}
    assert {b.claim_id for b in page.groups[1].blocks} == {beta.id}


async def test_flat_lens_cached_sections_render_as_profile_list(store):
    alpha = await _claim(store, "alpha marker belongs in the directory", canonical_subject="User")
    beta = await _claim(store, "beta marker belongs in the directory", canonical_subject="User")
    page_md = (
        "# Records\n"
        f"## Record A\n- Alpha marker. <!--claim:{alpha.id}-->\n\n"
        f"## Record B\n- Beta marker. <!--claim:{beta.id}-->\n"
    )
    lens = await _lens(store, name="Records", criterion="approved record entries", page=page_md)
    await _member(store, lens.id, alpha)
    await _member(store, lens.id, beta)

    cheap = FakeCompletionClient()
    strong = FakeCompletionClient()
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert cheap.calls == []
    assert strong.calls == []
    assert page.markdown == page_md
    assert page.groups is not None
    assert [g.subject for g in page.groups] == ["Record A", "Record B"]
    assert {b.claim_id for b in page.groups[0].blocks} == {alpha.id}
    assert {b.claim_id for b in page.groups[1].blocks} == {beta.id}
    assert {b.claim_id for b in page.blocks} == {alpha.id, beta.id}


async def test_project_cache_hit_costs_zero_synthesis(store):
    c1 = await _claim(store, "user runs 5k")
    page_md = f"# Health\n## Profile\n- Runs 5k. <!--claim:{c1.id}-->\n"
    lens = await _lens(store, name="Health", criterion="health", page=page_md, detail=LensDetailLevel.STRUCTURED)
    await _member(store, lens.id, c1)

    cheap = FakeCompletionClient()
    strong = FakeCompletionClient()
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.synthesized is True
    assert page.markdown == page_md
    # Cache hit: no re-validation judge call, no synthesis call.
    assert cheap.calls == []
    assert strong.calls == []
    assert page.groups is None
    assert {b.claim_id for b in page.blocks} == {c1.id}


# --- grouped-by-subject projection (presentation only) ---------------


async def test_grouped_projection_buckets_by_canonical_subject(store):
    from ntrp.memory.models import LensRenderMode

    lens = await _lens(
        store,
        name="Subjects",
        criterion="claims about subjects",
        render_mode=LensRenderMode.GROUPED_BY_SUBJECT,
    )
    # Alpha has two claims, Beta one -> Alpha bucket leads (largest first).
    a1 = await _claim(store, "Alpha owns item one", canonical_subject="Alpha")
    a2 = await _claim(store, "Alpha owns item two", canonical_subject="Alpha")
    b1 = await _claim(store, "Beta owns item three", canonical_subject="Beta")
    for c in (a1, a2, b1):
        await _member(store, lens.id, c)

    cheap = KeywordJudge("alpha", "beta")  # all three stay `in`
    # One profile-synthesis call per subject bucket; echo that bucket's anchors.
    alpha_md = f"- Owns item one. <!--claim:{a1.id}-->\n- Owns item two. <!--claim:{a2.id}-->"
    beta_md = f"- Owns item three. <!--claim:{b1.id}-->"
    strong = FakeCompletionClient(queue=[_synth(alpha_md), _synth(beta_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.groups is not None
    subjects = [g.subject for g in page.groups]
    assert subjects == ["Alpha", "Beta"]  # largest bucket first
    alpha = page.groups[0]
    assert {b.claim_id for b in alpha.blocks} == {a1.id, a2.id}
    assert alpha.synthesized is True
    # Concatenated page markdown carries per-subject headings + all anchors.
    assert "## Alpha" in page.markdown and "## Beta" in page.markdown
    assert set(parse_anchors(page.markdown)) == {a1.id, a2.id, b1.id}
    # Grouped output is cached into the `page` slot as markdown (Lens spec §6).
    cached = (await store.get_lens(lens.id)).page
    assert cached == page.markdown


async def test_grouped_cache_hit_costs_zero_synthesis(store):
    """A grouped lens with a materialized page re-derives its groups from the cached
    markdown alone — no re-validation judge call, no profile synthesis (Lens spec §6).
    """
    from ntrp.memory.models import LensRenderMode

    a1 = await _claim(store, "Alpha owns item one", canonical_subject="Alpha")
    a2 = await _claim(store, "Alpha owns item two", canonical_subject="Alpha")
    b1 = await _claim(store, "Beta owns item three", canonical_subject="Beta")
    page_md = (
        "# Subjects\n*Lens · criterion: claims about subjects*\n\n"
        f"## Alpha\n- Owns item one. <!--claim:{a1.id}-->\n- Owns item two. <!--claim:{a2.id}-->\n\n"
        f"## Beta\n- Owns item three. <!--claim:{b1.id}-->"
    )
    lens = await _lens(
        store,
        name="Subjects",
        criterion="claims about subjects",
        page=page_md,
        render_mode=LensRenderMode.GROUPED_BY_SUBJECT,
    )
    for c in (a1, a2, b1):
        await _member(store, lens.id, c)

    cheap = FakeCompletionClient()
    strong = FakeCompletionClient()
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    # Cache hit: no judge call, no synthesis call.
    assert cheap.calls == []
    assert strong.calls == []
    assert page.synthesized is True
    assert page.markdown == page_md
    # Groups + blocks reconstructed from the cached markdown's `## {subject}` sections.
    assert [g.subject for g in page.groups] == ["Alpha", "Beta"]
    assert {b.claim_id for b in page.groups[0].blocks} == {a1.id, a2.id}
    assert {b.claim_id for b in page.groups[1].blocks} == {b1.id}
    assert {b.claim_id for b in page.blocks} == {a1.id, a2.id, b1.id}


async def test_grouped_cache_skips_negative_examples_section(store):
    """The write-back REJECT negative-examples section is not a subject group; the
    cached-grouped reconstruction must ignore it (it carries no anchors anyway)."""
    from ntrp.memory.models import LensRenderMode

    a1 = await _claim(store, "Alpha owns item one", canonical_subject="Alpha")
    page_md = (
        "# Subjects\n*Lens · criterion: claims about subjects*\n\n"
        f"## Alpha\n- Owns item one. <!--claim:{a1.id}-->\n\n"
        f"{NEGATIVE_EXAMPLES_HEADER}\n- user drives a tesla\n"
    )
    lens = await _lens(
        store,
        name="Subjects",
        criterion="claims about subjects",
        page=page_md,
        render_mode=LensRenderMode.GROUPED_BY_SUBJECT,
    )
    await _member(store, lens.id, a1)

    proj = _projector(store, cheap=FakeCompletionClient(), strong=FakeCompletionClient())
    page = await proj.project(lens.id)

    assert [g.subject for g in page.groups] == ["Alpha"]
    assert {b.claim_id for b in page.blocks} == {a1.id}


async def test_grouped_profile_synthesis_failure_degrades_that_bucket(store):
    from ntrp.memory.models import LensRenderMode

    lens = await _lens(
        store,
        name="Subjects",
        criterion="claims about subjects",
        render_mode=LensRenderMode.GROUPED_BY_SUBJECT,
    )
    c = await _claim(store, "Alpha owns item one", canonical_subject="Alpha")
    await _member(store, lens.id, c)

    cheap = KeywordJudge("alpha")
    strong = FakeCompletionClient(queue=[""])  # empty -> profile synth raises
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.groups is not None and len(page.groups) == 1
    grp = page.groups[0]
    assert grp.synthesized is False  # degraded to raw anchored list
    assert c.id in set(parse_anchors(grp.markdown))
    assert "Alpha owns item one" in grp.markdown


# --- §9.5 synthesis failure -> raw anchored list ---------------------


async def test_project_synthesis_failure_degrades_to_raw_list(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k every morning")
    await _member(store, lens.id, c1)

    cheap = KeywordJudge("user")
    # strong returns empty content -> synthesis raises -> raw fallback.
    strong = FakeCompletionClient(queue=[""])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.synthesized is False
    assert page.markdown  # never blank
    assert c1.id in set(parse_anchors(page.markdown))
    assert "user runs 5k every morning" in page.markdown


# --- anchor injection: synthesis must NOT echo opaque ids -----------
# These DEFEAT the old stub that echoed `<!--claim:ID-->` verbatim — the exact
# reason the raw-fallback bug shipped. A faithful model cites the numbered `[n]`
# tag it was given (it never sees the opaque id); the projector injects anchors
# deterministically post-synthesis. Synthesized must be True with anchors present.


class _IndexCitingSynth:
    """A real-model-like synth stub: returns clean markdown that cites claims by
    the `[n]` index tag it was shown, and NEVER emits a `<!--claim:ID-->` anchor.
    It reads the numbered ITEMS out of the prompt so it cites exactly the claims it
    was given, in order — proving anchoring no longer depends on id-echo."""

    def __init__(self):
        self.calls: list[dict] = []

    async def completion(self, *, messages, model, response_format=None, **kwargs):
        from tests.conftest import completion_response

        self.calls.append({"messages": messages, "model": model})
        user = messages[-1]["content"]
        lines = []
        for line in user.splitlines():
            s = line.strip()
            if not (s.startswith("{{") and "}}" in s):
                continue
            try:
                idx = int(s[2 : s.index("}}")])
            except ValueError:
                continue
            # Clean prose + the index tag. No opaque anchor anywhere.
            lines.append(f"- A faithfully synthesized line. {{{{{idx}}}}}")
        md = "## Profile\n" + "\n".join(lines)
        assert "<!--claim:" not in md  # the stub provably drops opaque anchors
        return completion_response(_synth(md).model_dump_json())


async def test_synthesis_without_anchor_echo_still_renders(store):
    lens = await _lens(store, name="Health", criterion="claims about the user's health")
    c1 = await _claim(store, "user runs 5k every morning")
    c2 = await _claim(store, "user takes vitamin D")
    await _member(store, lens.id, c1)
    await _member(store, lens.id, c2)

    cheap = KeywordJudge("user")
    strong = _IndexCitingSynth()  # cites [0]/[1], never echoes anchors
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    # The page is genuinely synthesized (NOT the raw bullet fallback)...
    assert page.synthesized is True
    # ...and anchors were INJECTED deterministically from the [n] citations.
    assert set(parse_anchors(page.markdown)) == {c1.id, c2.id}
    assert "<!--claim:" in page.markdown
    assert {b.claim_id for b in page.blocks} == {c1.id, c2.id}
    # the synthesized prose survived (not replaced by raw `- {content}` bullets).
    assert "faithfully synthesized" in page.markdown
    # and the structured page was cached for the next read.
    assert c1.id in (await store.get_lens(lens.id)).page


async def test_grouped_profile_without_anchor_echo_still_renders(store):
    from ntrp.memory.models import LensRenderMode

    lens = await _lens(
        store,
        name="Subjects",
        criterion="claims about subjects",
        render_mode=LensRenderMode.GROUPED_BY_SUBJECT,
    )
    a1 = await _claim(store, "Alpha owns item one", canonical_subject="Alpha")
    a2 = await _claim(store, "Alpha owns item two", canonical_subject="Alpha")
    b1 = await _claim(store, "Beta owns item three", canonical_subject="Beta")
    for c in (a1, a2, b1):
        await _member(store, lens.id, c)

    cheap = KeywordJudge("alpha", "beta")
    strong = _IndexCitingSynth()  # one call per bucket, cites by index, no anchors
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.groups is not None
    assert all(g.synthesized for g in page.groups)  # no raw fallback
    assert set(parse_anchors(page.markdown)) == {a1.id, a2.id, b1.id}
    assert "<!--claim:" in page.markdown


async def test_synthesis_citing_no_claims_degrades_to_raw(store):
    """Genuine failure guard: a synthesis that cites NO claim at all (neither a
    `[n]` tag nor an anchor) is not faithful -> raw anchored fallback, never blank."""
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k every morning")
    await _member(store, lens.id, c1)

    cheap = KeywordJudge("user")
    # well-formed markdown, but it references nothing it was given.
    strong = FakeCompletionClient(queue=[_synth("## Profile\n- Some unrelated prose.")])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id)

    assert page.synthesized is False
    assert c1.id in set(parse_anchors(page.markdown))  # raw fallback still anchored
    assert "user runs 5k every morning" in page.markdown


# --- re-validate-at-read after criterion narrows --------------------


async def test_revalidate_hides_now_out_member(store):
    lens = await _lens(store, name="Health", criterion="health")
    keep = await _claim(store, "user runs 5k every morning")
    drop = await _claim(store, "user drives a tesla")
    await _member(store, lens.id, keep)
    await _member(store, lens.id, drop)

    # criterion narrowed -> re-validation keeps only the running claim, drops the car.
    cheap = KeywordJudge("runs")  # "user runs 5k" -> in; "user drives a tesla" -> out
    synth_md = f"# Health\n## Profile\n- Runs 5k. <!--claim:{keep.id}-->\n"
    strong = FakeCompletionClient(queue=[_synth(synth_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id, refresh=True)

    # only still-`in` renders...
    assert set(parse_anchors(page.markdown)) == {keep.id}
    assert {b.claim_id for b in page.blocks} == {keep.id}
    # ...the now-`out` member is no longer a cached `in` member...
    assert await _member_ids(store, lens.id) == {keep.id}
    # ...and the dropped claim itself survives, active (a lens owns no claims).
    assert (await store.get(drop.id)).status is Status.ACTIVE


async def test_revalidate_drops_verdicts_if_criterion_edited_mid_pass(store):
    # A criterion edit landing during _revalidate's judge await must not let it cache
    # OLD-criterion verdicts back into the just-cleared cache (mirrors the guard in
    # refresh_lens_cache). updated_at changed → drop the stale verdicts.
    from tests.conftest import completion_response

    lens = await _lens(store, name="Health", criterion="health")
    m1 = await _claim(store, "user runs 5k")
    await _member(store, lens.id, m1)
    captured = await store.get_lens(lens.id)  # the old criterion/updated_at

    class EditingJudge:
        def __init__(self):
            self.edited = False

        async def completion(self, *, messages, model, response_format=None, **kwargs):
            if not self.edited:
                self.edited = True
                await store.update_lens(lens.id, criterion="cardio only")  # bumps updated_at
            return completion_response(
                MembershipBatch(votes=[MembershipVote(item_index=0, decision="in", rationale="")]).model_dump_json()
            )

    proj = _projector(store, cheap=EditingJudge())
    kept = await proj._revalidate([m1], captured)

    assert kept == []  # stale verdicts not rendered
    assert await _member_ids(store, lens.id) == set()  # and not cached


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


# --- write-back: ACCEPT ----------------------------------------------


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


# --- write-back: EDIT -> supersede the claim -------------------------


async def test_edit_supersedes_claim(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 3k")
    await _member(store, lens.id, c1)
    wb = _writeback(store)

    res = await wb.apply(
        lens.id,
        [PageEditOp(kind=PageEditKind.EDIT, claim_id=c1.id, new_text="user runs 5k every morning")],
    )

    assert any(k is PageEditKind.EDIT for k, _ in res.applied)
    # predecessor superseded, successor active with the new text.
    assert (await store.get(c1.id)).status is Status.SUPERSEDED
    successor_id = next(k_id for k, k_id in res.applied if k is PageEditKind.EDIT)
    succ = await store.get(successor_id)
    assert succ.content == "user runs 5k every morning"
    assert succ.status is Status.ACTIVE
    assert succ.canonical_subject == c1.canonical_subject  # subject carried over
    # EDIT triggers a re-derive (membership recomputes on the next projection).
    assert res.rederive_triggered is True


# --- write-back: REJECT -> correction, claim + cache survive ---------


async def test_include_records_override_and_marks_dirty(store):
    lens = await _lens(store, name="Dex employees", criterion="strict employees", page="# Dex\n")
    c1 = await _claim(store, "Kevin Gu is a Dex collaborator.", canonical_subject="Kevin Gu")
    wb = _writeback(store)

    res = await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.INCLUDE, claim_id=c1.id)])

    assert (PageEditKind.INCLUDE, c1.id) in res.applied
    assert res.rederive_triggered is True
    assert c1.id in await store.get_inclusions(lens.id)
    assert await _member_ids(store, lens.id) == {c1.id}
    assert (await store.get_lens(lens.id)).page is None


async def test_include_then_project_keeps_claim_even_when_judge_would_drop_it(store):
    lens = await _lens(store, name="Dex employees", criterion="strict employees", page="# Dex\n")
    included = await _claim(store, "Kevin Gu is a Dex collaborator.", canonical_subject="Kevin Gu")
    wb = _writeback(store)
    await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.INCLUDE, claim_id=included.id)])
    await store.invalidate_lens_membership(lens.id)

    cheap = KeywordJudge("not-present")
    synth_md = f"# Dex employees\n## Kevin Gu\n- Collaborator. <!--claim:{included.id}-->\n"
    strong = FakeCompletionClient(queue=[_synth(synth_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id, refresh=True)

    assert set(parse_anchors(page.markdown)) == {included.id}
    assert {b.claim_id for b in page.blocks} == {included.id}


async def test_reject_records_correction_keeps_claim(store):
    lens = await _lens(store, name="Health", criterion="health", page="# Health\n")
    c1 = await _claim(store, "user drives a tesla")
    await _member(store, lens.id, c1)
    wb = _writeback(store)

    res = await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.REJECT, claim_id=c1.id)])

    assert (PageEditKind.REJECT, c1.id) in res.applied
    assert res.rederive_triggered is True
    # the claim survives active (a lens owns no claims).
    assert (await store.get(c1.id)).status is Status.ACTIVE
    # the rejection is recorded DURABLY (survives cache purges).
    assert c1.id in await store.get_rejections(lens.id)
    # the page cache is nulled so the next read re-derives without the claim.
    assert (await store.get_lens(lens.id)).page is None
    # the membership cache was invalidated so it re-derives on next read.
    assert await _member_ids(store, lens.id) == set()


async def test_reject_then_project_hides_claim(store):
    """Full loop: REJECT -> durable rejection + caches nulled -> next project
    excludes the rejected claim from the membership pool entirely (user override)
    -> page hides it; the claim survives globally."""
    lens = await _lens(store, name="Health", criterion="health", page="# Health\n")
    keep = await _claim(store, "user runs 5k every morning")
    rejected = await _claim(store, "user drives a tesla")
    await _member(store, lens.id, keep)
    await _member(store, lens.id, rejected)

    wb = _writeback(store)
    await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.REJECT, claim_id=rejected.id)])

    # next projection: refresh re-derives the cache, then re-validation keeps only
    # the running claim; the rejected car claim votes `out` at both judge passes.
    cheap = KeywordJudge("runs")
    synth_md = f"# Health\n## Profile\n- Runs 5k. <!--claim:{keep.id}-->\n"
    strong = FakeCompletionClient(queue=[_synth(synth_md)])
    proj = _projector(store, cheap=cheap, strong=strong)

    page = await proj.project(lens.id, refresh=True)

    assert set(parse_anchors(page.markdown)) == {keep.id}
    # claim survives active.
    assert (await store.get(rejected.id)).status is Status.ACTIVE


# --- write-back: no freeform ADD path -------------------------------


async def test_writeback_has_no_freeform_add_op():
    assert "add" not in {kind.value for kind in PageEditKind}


# --- write-back: EDIT_CRITERION -> in-place criterion update + dirty -


async def test_edit_criterion_updates_in_place_and_marks_dirty(store):
    page_md = "# Health\n## Profile\n_cached_\n"
    lens = await _lens(store, name="Health", criterion="health", page=page_md)
    c1 = await _claim(store, "user runs 5k")
    await _member(store, lens.id, c1)  # a stale membership row to be invalidated
    wb = _writeback(store)

    res = await wb.apply(
        lens.id,
        [PageEditOp(kind=PageEditKind.EDIT_CRITERION, new_text="cardiovascular health only")],
    )

    assert any(k is PageEditKind.EDIT_CRITERION for k, _ in res.applied)
    # in-place update: same row id, new criterion, page nulled (dirty -> re-derive).
    updated = await store.get_lens(lens.id)
    assert updated.criterion == "cardiovascular health only"
    assert updated.page is None  # dirty signal
    # The membership cache is invalidated (file written first, invalidate last).
    assert await store.get_membership(lens.id) == []


# --- stale anchor -> rejected, no silent write -----------------------


async def test_stale_anchor_op_is_rejected(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k")
    await _member(store, lens.id, c1)
    await store.invalidate(c1.id, status=Status.SUPERSEDED)  # claim moved out from under us
    wb = _writeback(store)

    res = await wb.apply(lens.id, [PageEditOp(kind=PageEditKind.EDIT, claim_id=c1.id, new_text="user runs 10k")])

    assert res.applied == []
    assert len(res.rejected) == 1
    op, reason = res.rejected[0]
    assert op.kind is PageEditKind.EDIT
    assert "re-open" in reason


# --- apply order + partial failure -----------------------------------


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
    return LensWriteBack(store)
