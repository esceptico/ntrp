"""Tests for WriteSeam (CONTRACTS.md §10).

The seam is the shared admit->write entry. It owns scope/SourceRef plumbing and
the bypass_admit asymmetry, then delegates the ADD/NOOP/CONTRADICT decision to
the ONE Reconciler. These tests stub Reconciler and AdmitGate so the seam is
exercised in isolation against the real (in-memory) Stage-2 store. NEVER touches
~/.ntrp/memory.db — store fixture is aiosqlite ':memory:'.
"""

from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.models import Provenance, Scope, ScopeKind, SourceRef
from ntrp.memory.pipeline.types import (
    AdmitResult,
    CaptureUnit,
    Op,
    ReconcileResult,
    Verdict,
)
from ntrp.memory.pipeline.write import WriteOutcome, WriteRequest, WriteSeam
from ntrp.memory.store import MemoryStore

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db")
    s = MemoryStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


class StubAdmit:
    """Records the unit it saw and returns a scripted verdict + candidates."""

    def __init__(self, *, verdict=Verdict.ADMIT, candidates=None, reason="stub"):
        self.verdict = verdict
        self.candidates = candidates or []
        self.reason = reason
        self.seen: list[CaptureUnit] = []

    async def admit(self, unit: CaptureUnit) -> AdmitResult:
        self.seen.append(unit)
        # A forced unit always ADMITs (CONTRACTS §5 tier 1).
        verdict = Verdict.ADMIT if unit.forced else self.verdict
        return AdmitResult(
            verdict=verdict,
            unit=unit,
            residual=unit.exchanges[0].text if verdict is Verdict.ADMIT else None,
            reason=self.reason,
            candidates=self.candidates,
            forced=unit.forced,
        )


class StubReconciler:
    """Records the call and returns a scripted ReconcileResult."""

    def __init__(self, *, result=None, raise_exc=None):
        self.result = result
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def reconcile(self, candidates, scope, *, prior_candidates=None):
        self.calls.append(
            {
                "candidates": candidates,
                "scope": scope,
                "prior_candidates": prior_candidates,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.result is None:
            return []
        return [self.result]


USER_SCOPE = Scope(kind=ScopeKind.USER)
REF = SourceRef(kind="chat_turn", ref="run-1")


def _req(content="I switched to Linux", *, bypass_admit=True, scope=USER_SCOPE):
    return WriteRequest(
        content=content,
        scope=scope,
        provenance=Provenance.USER_AUTHORED,
        source_refs=[REF],
        bypass_admit=bypass_admit,
    )


async def test_add_returns_written_outcome(store):
    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.ADD, subject_lens_id="lens-1", written_id="claim-1"
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    out = await seam.admit_and_write(_req())
    assert out == WriteOutcome(written=True, item_id="claim-1", reason="Remembered.")


async def test_noop_reports_not_written_but_keeps_target(store):
    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0,
            op=Op.NOOP,
            subject_lens_id="lens-1",
            target_claim_id="claim-old",
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    out = await seam.admit_and_write(_req())
    assert out.written is False
    assert out.item_id == "claim-old"
    assert out.reason == "Already known (corroborated)."


async def test_contradict_reports_supersede(store):
    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0,
            op=Op.CONTRADICT,
            subject_lens_id="lens-1",
            written_id="claim-new",
            target_claim_id="claim-old",
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    out = await seam.admit_and_write(_req())
    assert out.written is True
    assert out.item_id == "claim-new"
    assert "superseded" in out.reason


async def test_bypass_admit_always_reaches_reconcile_even_on_reject_verdict(store):
    # remember() sets bypass_admit=True. Even an admit gate scripted to REJECT
    # must not stop the write — the forced unit ADMITs and reconcile runs.
    admit = StubAdmit(verdict=Verdict.REJECT)
    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.ADD, subject_lens_id="l", written_id="c-1"
        )
    )
    seam = WriteSeam(store, rec, admit)
    out = await seam.admit_and_write(_req(bypass_admit=True))
    assert out.written is True
    assert len(rec.calls) == 1
    # the unit Admit saw was forced
    assert admit.seen[0].forced is True


async def test_non_bypass_reject_skips_reconcile(store):
    # A non-user writer (bypass_admit=False) that fails the worth-gate must NOT
    # reach Reconcile and must not write.
    admit = StubAdmit(verdict=Verdict.REJECT, reason="predictable")
    rec = StubReconciler(result=None)
    seam = WriteSeam(store, rec, admit)
    out = await seam.admit_and_write(_req(bypass_admit=False))
    assert out.written is False
    assert "not admitted" in out.reason
    assert rec.calls == []


async def test_non_bypass_admit_passes_candidates_as_prior(store):
    from ntrp.memory.models import Kind, MemoryItem

    incumbent = MemoryItem(
        id="prior-1",
        kind=Kind.CLAIM,
        content="prior fact",
        scope=USER_SCOPE,
        provenance=Provenance.RECORDED,
    )
    admit = StubAdmit(verdict=Verdict.ADMIT, candidates=[incumbent])
    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.ADD, subject_lens_id="l", written_id="c-1"
        )
    )
    seam = WriteSeam(store, rec, admit)
    await seam.admit_and_write(_req(bypass_admit=False))
    assert rec.calls[0]["prior_candidates"] == [incumbent]


async def test_reconcile_failure_does_not_fabricate_id(store):
    admit = StubAdmit()
    rec = StubReconciler(raise_exc=RuntimeError("llm down"))
    seam = WriteSeam(store, rec, admit)
    out = await seam.admit_and_write(_req())
    assert out.written is False
    assert out.item_id is None
    assert "reconcile failed" in out.reason


async def test_empty_content_short_circuits(store):
    rec = StubReconciler()
    seam = WriteSeam(store, rec, StubAdmit())
    out = await seam.admit_and_write(_req(content="   "))
    assert out.written is False
    assert out.reason == "empty content"
    assert rec.calls == []


async def test_candidate_carries_request_fields(store):
    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.ADD, subject_lens_id="l", written_id="c-1"
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    await seam.admit_and_write(_req(content="  I run marathons  "))
    cand = rec.calls[0]["candidates"][0]
    assert cand.content == "I run marathons"  # stripped
    assert cand.provenance is Provenance.USER_AUTHORED
    assert cand.source_refs == [REF]
    assert cand.scope == USER_SCOPE


async def test_empty_reconcile_list_reports_no_result(store):
    rec = StubReconciler(result=None)  # returns []
    seam = WriteSeam(store, rec, StubAdmit())
    out = await seam.admit_and_write(_req())
    assert out.written is False
    assert "no result" in out.reason


# --- remember() tool -------------------------------------------------


def _execution(seam, *, project=None):
    from ntrp.tools.memory import MEMORY_WRITE_SERVICE

    class _Run:
        run_id = "run-1"

    class _State:
        session_id = "sess-1"

    class _Ctx:
        def __init__(self):
            self.services = {MEMORY_WRITE_SERVICE: seam} if seam is not None else {}
            self.project = project
            self.run = _Run()
            self.session_state = _State()

        @property
        def session_id(self):
            return self.session_state.session_id

    class _Exec:
        def __init__(self):
            self.tool_id = "tool-1"
            self.tool_name = "remember"
            self.ctx = _Ctx()

    return _Exec()


async def test_remember_tool_writes_via_seam_with_user_scope(store):
    from ntrp.tools.memory import RememberInput, remember

    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.ADD, subject_lens_id="l", written_id="c-1"
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    res = await remember(_execution(seam), RememberInput(fact="I switched to Linux"))
    assert res.is_error is False
    assert "Remembered" in res.content
    # bypass_admit is set and scope is USER (no project)
    call = rec.calls[0]
    assert call["scope"] == Scope(kind=ScopeKind.USER)


async def test_remember_tool_uses_project_scope_when_present(store):
    from ntrp.tools.memory import RememberInput, remember

    class _Project:
        project_id = "proj-42"

    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.ADD, subject_lens_id="l", written_id="c-1"
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    await remember(_execution(seam, project=_Project()), RememberInput(fact="ships Friday"))
    assert rec.calls[0]["scope"] == Scope(kind=ScopeKind.PROJECT, key="proj-42")


async def test_remember_tool_noop_is_not_an_error(store):
    from ntrp.tools.memory import RememberInput, remember

    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.NOOP, subject_lens_id="l", target_claim_id="old"
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    res = await remember(_execution(seam), RememberInput(fact="I use vim"))
    assert res.is_error is False
    assert "Already known" in res.content


async def test_remember_tool_without_service_errors(store):
    from ntrp.tools.memory import RememberInput, remember

    res = await remember(_execution(None), RememberInput(fact="anything"))
    assert res.is_error is True
    assert "not available" in res.content


async def test_remember_tool_reconcile_failure_is_error(store):
    from ntrp.tools.memory import RememberInput, remember

    rec = StubReconciler(raise_exc=RuntimeError("llm down"))
    seam = WriteSeam(store, rec, StubAdmit())
    res = await remember(_execution(seam), RememberInput(fact="something"))
    assert res.is_error is True
    assert "reconcile failed" in res.content


async def test_remember_tool_source_ref_points_at_chat_turn(store):
    from ntrp.tools.memory import RememberInput, remember

    rec = StubReconciler(
        result=ReconcileResult(
            claim_index=0, op=Op.ADD, subject_lens_id="l", written_id="c-1"
        )
    )
    seam = WriteSeam(store, rec, StubAdmit())
    await remember(_execution(seam), RememberInput(fact="I like espresso"))
    cand = rec.calls[0]["candidates"][0]
    assert cand.source_refs[0].kind == "chat_turn"
    assert cand.source_refs[0].ref == "sess-1:tool-1"
    assert cand.provenance is Provenance.USER_AUTHORED
