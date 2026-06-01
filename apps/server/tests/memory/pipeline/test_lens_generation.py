"""Async lens-page generation — the GET must NOT block on synthesis.

DEFEATS the instant stub that made the timeout bug invisible: the synth stub here
is SLOW (awaits an event the test controls) so a blocking GET would hang for the
whole synthesis. We prove:
  - cache miss -> `ensure` returns a `generating` status FAST (synthesis still
    running in the background), then completes and caches the page;
  - progress is reported (scoring -> synthesizing/subject -> ready);
  - a clean cache hit returns the page synchronously with NO generation/progress;
  - the router GET returns 202 on a miss (never 200-after-blocking) and 200 on hit.

Tmp in-memory SQLite only; LLMs are offline stubs; never ~/.ntrp/memory.db.
"""

import asyncio
import uuid

import aiosqlite
import httpx
import pytest_asyncio

from ntrp.memory.models import (
    LensDetailLevel,
    LensProvenance,
    LensRenderMode,
    LensRow,
    MembershipDecision,
    MembershipVerdict,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
)
from ntrp.memory.pipeline.lens_generation import LensGenStage, LensPageGenerator
from ntrp.memory.pipeline.project import LensProjector, parse_anchors
from ntrp.memory.pipeline.prompts_project import PageSynthesis
from ntrp.memory.pipeline.prompts_reconcile import MembershipBatch, MembershipVote
from ntrp.memory.store import MemoryStore
from ntrp.server.app import app
from ntrp.server.deps import require_knowledge_runtime
from tests.conftest import FakeEmbedder, completion_response

USER = Scope(kind=ScopeKind.USER)


@pytest_asyncio.fixture
async def store():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


async def _claim(store, content, **kw):
    c = MemoryItem(
        id=uuid.uuid4().hex,
        content=content,
        canonical_subject=kw.pop("canonical_subject", "Tim"),
        scope=USER,
        provenance=Provenance.RECORDED,
        **kw,
    )
    return await store.create_item(c)


async def _lens(store, *, name, criterion, page=None, render_mode=None):
    le = LensRow(
        id=uuid.uuid4().hex,
        name=name,
        criterion=criterion,
        scope=USER,
        provenance=LensProvenance.USER_AUTHORED,
        detail_level=LensDetailLevel.STRUCTURED,
        render_mode=render_mode or LensRenderMode.FLAT,
        page=page,
    )
    return await store.create_lens_row(le)


async def _member(store, lens_id, claim):
    await store.put_membership(
        [MembershipVerdict(lens_id=lens_id, claim_id=claim.id, decision=MembershipDecision.IN)]
    )


class _AllInJudge:
    """Votes every item `in` (content-blind). Used to keep all seeded members."""

    async def completion(self, *, messages, model, response_format=None, **kwargs):
        user = messages[-1]["content"]
        votes = []
        for line in user.splitlines():
            s = line.strip()
            if s.startswith("[") and "]" in s:
                try:
                    votes.append(MembershipVote(item_index=int(s[1 : s.index("]")]), decision="in", rationale=""))
                except ValueError:
                    pass
        return completion_response(MembershipBatch(votes=votes).model_dump_json())


class _SlowIndexSynth:
    """Synth stub that BLOCKS on an event until the test releases it, then returns
    clean index-cited markdown (no opaque anchors). A blocking GET would hang on
    this for the full synthesis; the async path must not."""

    def __init__(self):
        self.gate = asyncio.Event()
        self.calls = 0

    async def completion(self, *, messages, model, response_format=None, **kwargs):
        self.calls += 1
        await self.gate.wait()
        user = messages[-1]["content"]
        lines = []
        for line in user.splitlines():
            s = line.strip()
            if s.startswith("[") and "]" in s:
                try:
                    idx = int(s[1 : s.index("]")])
                except ValueError:
                    continue
                lines.append(f"- Synthesized line. [{idx}]")
        md = "## Profile\n" + "\n".join(lines)
        return completion_response(PageSynthesis(markdown=md).model_dump_json())


def _gen(store, cheap, strong):
    proj = LensProjector(
        store, FakeEmbedder(), cheap, strong, cheap_model="cheap", strong_model="strong"
    )
    return LensPageGenerator(proj)


# --- generator: non-blocking + progress ------------------------------


async def test_ensure_returns_generating_then_completes(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k")
    await _member(store, lens.id, c1)

    strong = _SlowIndexSynth()
    gen = _gen(store, _AllInJudge(), strong)

    # Synthesis is gated (blocked) -> ensure must return a status, not the page,
    # without waiting for synthesis to finish.
    result = await asyncio.wait_for(gen.ensure(lens.id, detail=None, refresh=False), timeout=0.5)
    from ntrp.memory.pipeline.types import ProjectedPage

    assert not isinstance(result, ProjectedPage)
    assert result.stage in (LensGenStage.CREATING, LensGenStage.SCORING, LensGenStage.SYNTHESIZING)

    # Let the background generation run to completion.
    strong.gate.set()
    await gen.drain()
    assert strong.calls == 1  # synthesis ran exactly once, in the background

    # Status is READY and the page is now a clean cache hit (no further synthesis).
    assert gen.status(lens.id).stage is LensGenStage.READY
    page = await gen.ensure(lens.id, detail=None, refresh=False)
    assert isinstance(page, ProjectedPage)
    assert page.synthesized is True
    assert c1.id in set(parse_anchors(page.markdown))


async def test_ensure_reports_per_subject_progress(store):
    lens = await _lens(
        store, name="People", criterion="people", render_mode=LensRenderMode.GROUPED_BY_SUBJECT
    )
    r1 = await _claim(store, "Regina is CEO", canonical_subject="Regina")
    r2 = await _claim(store, "Regina judged a hackathon", canonical_subject="Regina")
    k1 = await _claim(store, "Kevin is an engineer", canonical_subject="Kevin")
    for c in (r1, r2, k1):
        await _member(store, lens.id, c)

    strong = _SlowIndexSynth()
    gen = _gen(store, _AllInJudge(), strong)

    await gen.ensure(lens.id, detail=None, refresh=False)
    # While the first subject's synthesis is gated, status shows synthesizing + the
    # subject + an i/n progress marker.
    async def _wait_synth():
        while True:
            st = gen.status(lens.id)
            if st and st.stage is LensGenStage.SYNTHESIZING and st.subject is not None:
                return st
            await asyncio.sleep(0.005)

    st = await asyncio.wait_for(_wait_synth(), timeout=1.0)
    assert st.subject in ("Regina", "Kevin")
    assert st.progress and "/" in st.progress

    strong.gate.set()
    await gen.drain()
    assert gen.status(lens.id).stage is LensGenStage.READY


async def test_cache_hit_returns_page_no_generation(store):
    c1 = await _claim(store, "user runs 5k")
    page_md = f"# Health\n## Profile\n- Runs 5k. <!--claim:{c1.id}-->\n"
    lens = await _lens(store, name="Health", criterion="health", page=page_md)
    await _member(store, lens.id, c1)

    strong = _SlowIndexSynth()
    gen = _gen(store, _AllInJudge(), strong)

    from ntrp.memory.pipeline.types import ProjectedPage

    result = await gen.ensure(lens.id, detail=None, refresh=False)
    assert isinstance(result, ProjectedPage)  # synchronous cache hit
    assert result.markdown == page_md
    assert strong.calls == 0  # no synthesis
    assert gen.status(lens.id) is None  # no generation status recorded


async def test_generation_error_surfaces_in_status(store):
    """A genuine generation failure (projector raises, not a recoverable synthesis
    miss) surfaces as ERROR with the message — the background loop never crashes."""
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k")
    await _member(store, lens.id, c1)

    gen = _gen(store, _AllInJudge(), _SlowIndexSynth())

    async def _boom(*args, **kwargs):
        raise RuntimeError("projector exploded")

    gen.projector.project = _boom  # the whole generation step blows up
    await gen.ensure(lens.id, detail=None, refresh=False)
    await gen.drain()
    st = gen.status(lens.id)
    assert st.stage is LensGenStage.ERROR
    assert "projector exploded" in st.error


# --- router: 202 on miss, 200 on hit, status endpoint ----------------


class _RealishKnowledge:
    def __init__(self, store, gen):
        self.memory = store
        self.memory_retrieval = type("P", (), {"lens_generator": gen})()

    @property
    def memory_ready(self):
        return True


def _async_client() -> httpx.AsyncClient:
    # ASGITransport drives the app in THIS event loop, so the route's background
    # generation task is awaitable via gen.drain() (a TestClient runs its own loop
    # in a worker thread, which would orphan the create_task'd generation).
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_router_get_returns_202_on_miss_not_blocking(store):
    lens = await _lens(store, name="Health", criterion="health")
    c1 = await _claim(store, "user runs 5k")
    await _member(store, lens.id, c1)
    strong = _SlowIndexSynth()  # gated: a blocking GET would hang here
    gen = _gen(store, _AllInJudge(), strong)

    knowledge = _RealishKnowledge(store, gen)
    app.dependency_overrides[require_knowledge_runtime] = lambda: knowledge
    try:
        async with _async_client() as client:
            resp = await asyncio.wait_for(
                client.get(f"/admin/memory/lenses/{lens.id}/page"), timeout=0.5
            )
            # 202 Accepted with a generating status — NOT a 200 after blocking on synth.
            assert resp.status_code == 202
            body = resp.json()
            assert body["lens_id"] == lens.id
            assert body["status"] in ("creating", "scoring", "synthesizing")
            assert "markdown" not in body  # it's a status, not a ProjectedPage

            # The status endpoint reflects in-flight generation.
            s = await client.get(f"/admin/memory/lenses/{lens.id}/page/status")
            assert s.status_code == 200
            assert s.json()["stage"] in ("creating", "scoring", "synthesizing")

            # Release synthesis, drain, then a re-GET is a cache hit -> 200 page.
            strong.gate.set()
            await gen.drain()
            resp2 = await client.get(f"/admin/memory/lenses/{lens.id}/page")
            assert resp2.status_code == 200
            assert resp2.json()["synthesized"] is True
            assert c1.id in [b["claim_id"] for b in resp2.json()["blocks"]]
    finally:
        app.dependency_overrides.pop(require_knowledge_runtime, None)


async def test_router_get_404_on_missing_lens(store):
    gen = _gen(store, _AllInJudge(), _SlowIndexSynth())
    knowledge = _RealishKnowledge(store, gen)
    app.dependency_overrides[require_knowledge_runtime] = lambda: knowledge
    try:
        async with _async_client() as client:
            assert (await client.get("/admin/memory/lenses/ghost/page")).status_code == 404
            assert (await client.get("/admin/memory/lenses/ghost/page/status")).status_code == 404
    finally:
        app.dependency_overrides.pop(require_knowledge_runtime, None)
