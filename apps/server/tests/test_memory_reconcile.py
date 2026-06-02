"""Unit tests for the Stage-3 Reconcile component.

In-memory tmp DBs ONLY (never ~/.ntrp/memory.db). LLM + embedder are stubbed so
the store calls and the op mapping are exercised deterministically.

Subject coreference is a claim ATTRIBUTE (`canonical_subject`), not an entity
row: there are no lens rows, no member_of edges. Identity is decided by the LLM
judge over the embedding+FTS-recalled candidate set — never by a pronoun list, a
proper-noun regex, or a cosine threshold. These tests assert that contract:
recall opens the candidate set, the judge closes it. The only categorical branch
is the empty recalled set (0 candidates -> NEW, no judge call).
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
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    SourceRef,
    Status,
    now_iso,
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
        self.last_subject_user: str | None = None

    @property
    def calls(self) -> int:
        return self.subject_calls + self.batch_calls

    async def completion(self, *, response_format, **kwargs) -> CompletionResponse:
        if response_format is SubjectResolution:
            self.subject_calls += 1
            self.last_subject_user = kwargs["messages"][-1]["content"]
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
async def store(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
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


async def _existing_claim(
    store, content, *, subject="Timur", prov=Provenance.RECORDED, refs=None, scope=USER_SCOPE
) -> MemoryItem:
    """Seed an existing active claim for a subject. Subject is just an attribute;
    there is no entity row and no member_of edge to create."""
    claim = MemoryItem(
        id=uuid.uuid4().hex,
        content=content,
        canonical_subject=subject,
        scope=scope,
        provenance=prov,
        valid_from=now_iso(),
        source_refs=refs or [],
    )
    return await store.create_item(claim)


# --- tests ----------------------------------------------------------


async def test_new_subject_kept_when_no_candidates(store):
    # 0 recalled candidates is the only categorical branch: keep NEW, no judge call.
    cheap = StubLLM()
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur lives in Lisbon")], USER_SCOPE)

    assert cheap.subject_calls == 0  # no judge call when the recalled set is empty
    assert len(results) == 1
    r = results[0]
    assert r.op is Op.ADD
    assert r.subject_is_new is True
    assert r.canonical_subject == "Timur"
    assert r.written_id is not None

    claim = await store.get(r.written_id)
    assert claim is not None
    assert claim.canonical_subject == "Timur"
    assert claim.provenance is Provenance.RECORDED
    assert claim.source_refs  # grounding preserved


async def test_distinct_subjects_keeps_archived_only_subject_on_roster(store):
    # The coreference roster must retain a subject whose ONLY claim was archived
    # (bare archive / contradiction), so a re-emerging claim re-matches it instead of
    # fragmenting into a new canonical_subject. Active subjects still rank first.
    await _existing_claim(store, "Timur drinks tea", subject="Timur")
    gone = await _existing_claim(store, "Old project note", subject="ProjectX")
    await store.invalidate(gone.id, status=Status.ARCHIVED)

    roster = await store.distinct_subjects(USER_SCOPE)
    counts = dict(roster)
    assert counts.get("Timur") == 1
    assert "ProjectX" in counts  # archived-only subject still on the roster
    assert counts["ProjectX"] == 0  # zero active claims → ranked last
    assert roster[0][0] == "Timur"  # live subject first


async def test_recalled_candidate_goes_to_judge_who_matches(store):
    # A recalled candidate is decided by the LLM judge, not a heuristic. The judge
    # MATCHes the existing subject string — identity closes via the extractor's
    # canonical_subject + the judge, never a pronoun list. The pre-existing claim
    # means Phase 4 actually runs its batch call.
    await _existing_claim(store, "Timur drinks tea", subject="Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [_candidate("Timur likes espresso", subject="Timur", surfaces=["I"])], USER_SCOPE
    )

    assert results[0].subject_is_new is False
    assert results[0].canonical_subject == "Timur"
    # The identity judge fired (>=1 recalled candidate) and a Phase-4 batch ran.
    assert cheap.subject_calls == 1
    assert cheap.batch_calls == 1


async def test_lone_candidate_still_goes_to_judge_no_margin_shortcut(store):
    # A single recalled candidate must NOT auto-match: the judge always decides.
    await _existing_claim(store, "Espresso is a coffee drink", subject="Espresso")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Espresso", reason="same")
    )
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Espresso is great", subject="Espresso")], USER_SCOPE)

    assert results[0].canonical_subject == "Espresso"
    assert results[0].op is Op.ADD
    # The judge call fired even with one candidate — no cosine threshold shortcut.
    assert cheap.subject_calls == 1


async def test_update_supersedes_target(store):
    old = await _existing_claim(
        store, "Timur lives in Berlin", subject="Timur", refs=[SourceRef(kind="chat_turn", ref="old")]
    )
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
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
    existing = await _existing_claim(store, "Timur likes coffee", subject="Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
    cheap.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "noop", "target_idx": 0}])
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur likes coffee")], USER_SCOPE)

    assert results[0].op is Op.NOOP
    bumped = await store.get(existing.id)
    assert bumped.corroboration == 1
    assert bumped.status is Status.ACTIVE


async def test_contradict_archives_and_links_edge_no_successor_chain(store):
    old = await _existing_claim(store, "Timur is vegetarian", subject="Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
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
    # A contradiction is NOT a successor-chain (vision §4.4): the target is ARCHIVED
    # (validity closed), never SUPERSEDED, and there is no SUPERSEDES edge.
    assert (await store.get(old.id)).status is Status.ARCHIVED
    edges = await store.list_edges(r.written_id, direction="from")
    contradicts = [e for e in edges if e.role is EdgeRole.CONTRADICTS]
    assert old.id in {e.parent_id for e in contradicts}
    assert all(e.role is not EdgeRole.SUPERSEDES for e in edges)
    # the new claim is active.
    assert (await store.get(r.written_id)).status is Status.ACTIVE


async def test_user_authored_noop_over_inferred_confirms_not_supersedes(store):
    # The judge's NOOP is honored verbatim — a prior heuristic flipped it to UPDATE
    # when the incoming claim out-ranked the target on provenance, destructively
    # superseding an identical claim. Higher-provenance corroboration is recorded by
    # bumping corroboration + setting CONFIRMED feedback, NOT by rewriting the claim.
    from ntrp.memory.models import Feedback

    inferred = await _existing_claim(
        store, "Timur probably likes jazz", subject="Timur", prov=Provenance.INFERRED
    )
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
    cheap.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "noop", "target_idx": 0}])
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [_candidate("Timur likes jazz", prov=Provenance.USER_AUTHORED)], USER_SCOPE
    )

    assert results[0].op is Op.NOOP
    target = await store.get(inferred.id)
    assert target.status is Status.ACTIVE  # never destroyed
    assert target.corroboration == 1  # the provenance signal is recorded as corroboration
    assert target.feedback is Feedback.CONFIRMED  # user-authored confirms the inferred claim


async def test_invalid_target_idx_coerced_to_add(store):
    existing = await _existing_claim(store, "Timur lives in Berlin", subject="Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
    cheap.batch_queue.append(
        BatchReconcile(rows=[{"claim_index": 0, "op": "update", "target_idx": 99}])
    )
    rec = _reconciler(store, cheap)

    results = await rec.reconcile([_candidate("Timur enjoys hiking")], USER_SCOPE)

    assert results[0].op is Op.ADD  # bogus index never dead-ends
    assert (await store.get(existing.id)).status is Status.ACTIVE


async def test_hallucinated_match_subject_biases_to_new(store):
    # The judge MATCHes onto a canonical_subject that is not in the recalled set ->
    # self-correcting: keep the extractor's subject as NEW rather than trust it.
    await _existing_claim(store, "Timur plays chess", subject="Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Someone Else", reason="oops")
    )
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [_candidate("Tennis is a sport", subject="Tennis")], USER_SCOPE
    )

    r = results[0]
    assert r.subject_is_new is True  # hallucinated subject -> self-correcting NEW
    assert r.canonical_subject == "Tennis"


async def test_subject_batching_one_batch_per_group(store):
    # Two claims share one canonical subject and recall the same existing subject:
    # they group to ONE subject and a single Phase-4 batch call covers both (cost
    # is O(distinct subjects), not O(claims)).
    await _existing_claim(store, "Timur lives in Berlin", subject="Timur")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
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
    assert {r.canonical_subject for r in results} == {"Timur"}  # grouped to one subject
    # One batch call for the single subject group, regardless of claim count.
    assert cheap.batch_calls == 1


async def test_shallow_canonical_subject_reaches_judge_despite_busy_generic(store):
    # The User != Timur fragmentation root cause: a shallow canonical subject
    # ("Timur Ganiev", 1 claim) must still reach the identity judge even when a busy
    # generic subject ("the user", many claims) dominates every recall signal. The
    # roster guarantees it; the judge then MATCHes the incoming name fact onto it.
    await _existing_claim(store, "The user's name is Timur Ganiev", subject="Timur Ganiev")
    for n in range(20):
        await _existing_claim(store, f"The user did unrelated thing {n}", subject="the user")

    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur Ganiev", reason="same person")
    )
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    results = await rec.reconcile(
        [_candidate("Tim Ganiev is a nickname for the user", subject="Tim Ganiev", surfaces=["Tim"])],
        USER_SCOPE,
    )

    # The shallow canonical subject was offered to the judge (not trimmed by a cutoff)
    # and the judge resolved identity onto it.
    assert "Timur Ganiev" in cheap.last_subject_user
    assert results[0].canonical_subject == "Timur Ganiev"
    assert results[0].subject_is_new is False


async def test_identity_judge_receives_profile_gist_not_raw_claim(store):
    # The judge must see a profile gist (claim count + sample facts), not a single raw
    # example claim, so it can reason over accumulation (spec §4.4 / Lens §4 line 56).
    await _existing_claim(store, "The user prefers raw SQL", subject="the user")
    await _existing_claim(store, "The user lives in Lisbon", subject="the user")
    cheap = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="the user", reason="same")
    )
    cheap.batch_queue.append(BatchReconcile(rows=[{"claim_index": 0, "op": "add"}]))
    rec = _reconciler(store, cheap)

    await rec.reconcile([_candidate("The user is Timur", subject="the user")], USER_SCOPE)

    seen = cheap.last_subject_user
    assert "claims=2" in seen  # accumulation count surfaced
    assert "sample_facts=" in seen
    assert "prefers raw SQL" in seen  # a real sample fact, not just the name


async def test_escalation_uses_strong_model(store):
    high_trust = await _existing_claim(
        store, "Timur is allergic to peanuts", subject="Timur", prov=Provenance.USER_AUTHORED
    )
    cheap = StubLLM()
    strong = StubLLM()
    cheap.subject_queue.append(
        SubjectResolution(decision="MATCH", canonical_subject="Timur", reason="same")
    )
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
