"""Unit tests for the Stage-3 Reconcile component.

In-memory tmp DBs ONLY (never ~/.ntrp/memory.db). LLM + embedder are stubbed so
the store calls and the op mapping are exercised deterministically.

Identity is decided by the LLM judge over the embedding+FTS-recalled candidate
set — never by a pronoun list, a proper-noun regex, or a cosine threshold. These
tests assert that contract: recall opens the candidate set, the judge closes it.
The only categorical branch is the empty recalled set (0 candidates -> NEW).
"""

import hashlib
import uuid

import aiosqlite
import numpy as np
import pytest
import pytest_asyncio

from ntrp.agent.types.llm import Choice, CompletionResponse, FinishReason, Message, Role
from ntrp.agent.types.usage import Usage
from ntrp.memory.models import (
    EdgeRole,
    Kind,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    SourceRef,
    Status,
)
from ntrp.memory.pipeline.prompts_reconcile import BatchReconcile, SubjectResolution
from ntrp.memory.pipeline.reconcile import Reconciler
from ntrp.memory.pipeline.types import ClaimCandidate, Op
from ntrp.memory.store import MemoryStore

pytestmark = pytest.mark.asyncio

USER_SCOPE = Scope(kind=ScopeKind.USER)


# --- stubs ----------------------------------------------------------


def _response(payload_json: str) -> CompletionResponse:
    msg = Message(role=Role.ASSISTANT, content=payload_json, tool_calls=None, reasoning_content=None)
    return CompletionResponse(
        choices=[Choice(message=msg, finish_reason=FinishReason.STOP)],
        usage=Usage(),
        model="stub",
    )


class StubLLM:
    """Returns queued structured responses by response_format type."""

    def __init__(self):
        self.subject_queue: list[SubjectResolution] = []
        self.batch_queue: list[BatchReconcile] = []
        self.subject_calls = 0
        self.batch_calls = 0

    @property
    def calls(self) -> int:
        return self.subject_calls + self.batch_calls

    async def completion(self, *, response_format, **kwargs) -> CompletionResponse:
        if response_format is SubjectResolution:
            self.subject_calls += 1
            return _response(self.subject_queue.pop(0).model_dump_json())
        if response_format is BatchReconcile:
            self.batch_calls += 1
            return _response(self.batch_queue.pop(0).model_dump_json())
        raise AssertionError(f"unexpected response_format {response_format}")


class StubEmbedder:
    """Deterministic vectors keyed by a stable text hash; no network."""

    def __init__(self, dim: int = 8):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.dim)
        return v / (np.linalg.norm(v) or 1.0)

    async def embed_one(self, text: str) -> np.ndarray:
        return self._vec(text)

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([])
        return np.vstack([self._vec(t) for t in texts])


@pytest_asyncio.fixture
async def store():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


def _reconciler(store, cheap, strong=None, embed=None) -> Reconciler:
    return Reconciler(
        store,
        cheap,
        strong or cheap,
        embed or StubEmbedder(),
        cheap_model="cheap",
        strong_model="strong",
    )


def _candidate(
    content,
    *,
    prov=Provenance.RECORDED,
    subject="Timur",
    surfaces=None,
    scope=USER_SCOPE,
):
    return ClaimCandidate(
        content=content,
        source_refs=[SourceRef(kind="chat_turn", ref=uuid.uuid4().hex)],
        provenance=prov,
        canonical_subject=subject,
        subject_surfaces=surfaces or [],
        scope=scope,
    )


async def _entity_lens(store, name="Timur", criterion=None, scope=USER_SCOPE) -> MemoryItem:
    lens = MemoryItem(
        id=uuid.uuid4().hex,
        kind=Kind.LENS,
        content=name,
        scope=scope,
        provenance=Provenance.INDUCED,
        lens_kind="entity",
        lens_name=name,
        lens_criterion=criterion or f"this item is about {name}",
        lens_exclusive=True,
    )
    return await store.create_item(lens)


async def _member_claim(store, lens, content, *, prov=Provenance.RECORDED, refs=None) -> MemoryItem:
    claim = MemoryItem(
        id=uuid.uuid4().hex,
        kind=Kind.CLAIM,
        content=content,
        scope=USER_SCOPE,
        provenance=prov,
        source_refs=refs or [],
    )
    await store.create_item(claim)
    await store.add_edge(MemoryEdge(child_id=claim.id, parent_id=lens.id, role=EdgeRole.MEMBER_OF))
    return claim


# --- tests ----------------------------------------------------------


async def test_new_subject_minted_when_no_candidates(store):
    # 0 recalled candidates is the only categorical branch: mint NEW, no judge call.
    cheap = StubLLM()
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur lives in Lisbon")], USER_SCOPE)

    assert cheap.subject_calls == 0  # no judge call when the recalled set is empty
    assert len(results) == 1
    r = results[0]
    assert r.op is Op.ADD
    assert r.subject_created is True
    assert r.written_id is not None

    claim = await store.get(r.written_id)
    assert claim is not None and claim.kind is Kind.CLAIM
    assert claim.provenance is Provenance.RECORDED
    assert claim.source_refs  # grounding preserved

    lens = await store.get(r.subject_lens_id)
    assert lens.kind is Kind.LENS and lens.lens_kind == "entity"
    # Minted from the LLM-resolved canonical subject — never from raw content.
    assert lens.lens_name == "Timur"
    edges = await store.list_edges(r.written_id, direction="from", role=EdgeRole.MEMBER_OF)
    assert [e.parent_id for e in edges] == [r.subject_lens_id]


async def test_recalled_candidate_goes_to_judge_who_matches(store):
    # A recalled candidate is decided by the LLM judge, not a heuristic. The judge
    # MATCHes the existing lens — identity closes via the extractor's
    # canonical_subject + the judge, never a pronoun list. A pre-existing member
    # claim means Phase 4 actually runs its batch call.
    lens = await _entity_lens(store, name="Timur", criterion="this item is about Timur")
    await _member_claim(store, lens, "Timur drinks tea")
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [_candidate("Timur likes espresso", subject="Timur", surfaces=["I"])], USER_SCOPE
    )

    assert results[0].subject_created is False
    assert results[0].subject_lens_id == lens.id
    # The identity judge fired (>=1 recalled candidate) and a Phase-4 batch ran.
    assert cheap.subject_calls == 1
    assert cheap.batch_calls == 1


async def test_lone_candidate_still_goes_to_judge_no_margin_shortcut(store):
    # A single recalled candidate must NOT auto-match: the judge always decides.
    lens = await _entity_lens(store, name="Espresso", criterion="this item is about Espresso")
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Espresso is great", subject="Espresso")], USER_SCOPE)

    assert results[0].subject_lens_id == lens.id
    assert results[0].op is Op.ADD
    # The judge call fired even with one candidate — no cosine threshold shortcut.
    assert cheap.subject_calls == 1


async def test_update_supersedes_target(store):
    lens = await _entity_lens(store)
    old = await _member_claim(
        store, lens, "Timur lives in Berlin", refs=[SourceRef(kind="chat_turn", ref="old")]
    )
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.batch_queue.append(
        BatchReconcile(
            rows=[
                {"claim_index": 0, "op": "update", "target_idx": 0,
                 "merged_text": "Timur lives in Lisbon"}
            ]
        )
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur moved to Lisbon")], USER_SCOPE)

    r = results[0]
    assert r.op is Op.UPDATE
    assert r.target_claim_id == old.id
    successor = await store.get(r.written_id)
    assert successor.content == "Timur lives in Lisbon"
    assert (await store.get(old.id)).status is Status.SUPERSEDED
    assert "old" in {ref.ref for ref in successor.source_refs}  # evidence unioned


async def test_noop_bumps_corroboration(store):
    lens = await _entity_lens(store)
    existing = await _member_claim(store, lens, "Timur likes coffee")
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "noop", "target_idx": 0}])
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur likes coffee")], USER_SCOPE)

    assert results[0].op is Op.NOOP
    bumped = await store.get(existing.id)
    assert bumped.corroboration == 1
    assert bumped.status is Status.ACTIVE


async def test_contradict_supersedes_and_links_edge(store):
    lens = await _entity_lens(store)
    old = await _member_claim(store, lens, "Timur is vegetarian")
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.batch_queue.append(
        BatchReconcile(
            rows=[{"claim_index": 0, "op": "contradict", "target_idx": 0,
                   "merged_text": "Timur eats meat"}]
        )
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur eats meat now")], USER_SCOPE)

    r = results[0]
    assert r.op is Op.CONTRADICT
    assert (await store.get(old.id)).status is Status.SUPERSEDED
    contradicts = await store.list_edges(r.written_id, direction="from", role=EdgeRole.CONTRADICTS)
    assert old.id in {e.parent_id for e in contradicts}


async def test_user_authored_never_noops_over_inferred(store):
    lens = await _entity_lens(store)
    inferred = await _member_claim(
        store, lens, "Timur probably likes jazz", prov=Provenance.INFERRED
    )
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    # Model says NOOP, but incoming is user-authored over inferred -> coerced UPDATE.
    cheap.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "noop", "target_idx": 0}])
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [_candidate("Timur likes jazz", prov=Provenance.USER_AUTHORED)], USER_SCOPE
    )

    assert results[0].op is Op.UPDATE
    assert (await store.get(inferred.id)).status is Status.SUPERSEDED


async def test_invalid_target_idx_coerced_to_add(store):
    lens = await _entity_lens(store)
    existing = await _member_claim(store, lens, "Timur lives in Berlin")
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "update", "target_idx": 99}])
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur enjoys hiking")], USER_SCOPE)

    assert results[0].op is Op.ADD  # bogus index never dead-ends
    assert (await store.get(existing.id)).status is Status.ACTIVE


async def test_hallucinated_match_lens_id_biases_to_new(store):
    await _entity_lens(store, name="Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", lens_id="does-not-exist", reason="oops")
    )
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur plays tennis")], USER_SCOPE)

    r = results[0]
    assert r.subject_created is True  # invalid lens_id -> self-correcting NEW
    assert (await store.get(r.subject_lens_id)).lens_kind == "entity"


async def test_alias_added_on_match_feeds_the_lens(store):
    lens = await _entity_lens(store, name="Timur", criterion="this item is about Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", lens_id=lens.id, alias_to_add="TG", reason="same")
    )
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [_candidate("Timur prefers espresso", subject="Timur", surfaces=["TG"])], USER_SCOPE
    )

    assert results[0].subject_lens_id == lens.id
    # A genuinely new alias supersedes the lens with the surface appended to the
    # successor's criterion so the next recall is an exact FTS hit
    # (correction-feeds-the-lens). The old row persists (status=SUPERSEDED).
    assert (await store.get(lens.id)).status is Status.SUPERSEDED
    active = await store.query(kind=Kind.LENS, scope=USER_SCOPE, status=Status.ACTIVE)
    timur = [le for le in active if le.lens_name == "Timur"][0]
    assert "TG" in timur.lens_criterion


async def test_subject_batching_one_batch_per_group(store):
    # Two claims share one canonical subject and recall the same lens: they group
    # to ONE subject and a single Phase-4 batch call covers both (cost is
    # O(distinct subjects), not O(claims)).
    lens = await _entity_lens(store, name="Timur", criterion="this item is about Timur")
    await _member_claim(store, lens, "Timur lives in Berlin")
    cheap = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    cheap.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "add"}, {"claim_index": 1, "op": "add"}])
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [
            _candidate("Timur likes tea", subject="Timur"),
            _candidate("Timur runs daily", subject="Timur"),
        ],
        USER_SCOPE,
    )

    assert len(results) == 2
    assert all(r.op is Op.ADD for r in results)
    assert {r.subject_lens_id for r in results} == {lens.id}  # grouped to one subject
    # One batch call for the single subject group, regardless of claim count.
    assert cheap.batch_calls == 1


async def test_escalation_uses_strong_model(store):
    lens = await _entity_lens(store, name="Timur", criterion="this item is about Timur")
    high_trust = await _member_claim(
        store, lens, "Timur is allergic to peanuts", prov=Provenance.USER_AUTHORED
    )
    cheap = StubLLM()
    strong = StubLLM()
    cheap.subject_queue.append(SubjectResolution(decision="MATCH", lens_id=lens.id, reason="same"))
    # cheap proposes CONTRADICT against a user_authored target -> escalation
    cheap.batch_queue.append(
        BatchReconcile(
            rows=[{"claim_index": 0, "op": "contradict", "target_idx": 0,
                   "merged_text": "Timur is not allergic to peanuts"}]
        )
    )
    strong.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "noop", "target_idx": 0}])
    )
    rec = _reconciler(store, cheap, strong=strong)

    results = await rec.reconcile(
        [_candidate("maybe peanuts are fine", prov=Provenance.INFERRED, subject="Timur")],
        USER_SCOPE,
    )

    assert strong.batch_calls == 1
    assert results[0].escalated is True
    assert results[0].op is Op.NOOP  # strong model overrode to NOOP
    assert (await store.get(high_trust.id)).status is Status.ACTIVE
