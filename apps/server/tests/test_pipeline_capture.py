"""Capture-stage unit tests (CONTRACTS §4).

Tmp DBs ONLY — every store here is opened over an in-memory / tmp_path aiosqlite
connection. NEVER touches ~/.ntrp/memory.db.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from ntrp.memory.models import Scope, ScopeKind, SourceRef
from ntrp.memory.pipeline.capture import CaptureConfig, CaptureService
from ntrp.memory.pipeline.prompts_capture import SemanticBoundary
from ntrp.memory.pipeline.types import BoundaryKind, ExchangeRole
from ntrp.memory.store import MemoryStore

pytestmark = pytest.mark.asyncio


# --- fakes ------------------------------------------------------------------


@dataclass
class FakeSession:
    session_id: str
    messages: list[dict]
    last_activity: datetime
    session_type: str = "chat"
    origin_automation_id: str | None = None
    project_id: str | None = None


class FakeSessions:
    def __init__(self, sessions: dict[str, FakeSession]):
        self._sessions = sessions

    async def load_session(self, session_id: str):
        return self._sessions.get(session_id)


class FakeJudge:
    """Boundary judge that returns a scripted decision and counts calls."""

    def __init__(self, decision: SemanticBoundary | None):
        self.decision = decision
        self.calls = 0

    async def detect_boundary(self, *, system, user, model):
        self.calls += 1
        if self.decision is None:
            raise RuntimeError("boundary judge unavailable")
        return self.decision


def _msgs(*texts: str) -> list[dict]:
    out = []
    for i, t in enumerate(texts):
        out.append({"role": "user" if i % 2 == 0 else "assistant", "content": t})
    return out


_OPEN_CONNS: list[aiosqlite.Connection] = []


@pytest.fixture(autouse=True)
async def _close_conns():
    # Capture's _service() opens an aiosqlite :memory: store per test. The
    # connection spawns a NON-daemon worker thread; if it is never closed the
    # thread blocks interpreter shutdown, which is what made the pytest run hang
    # after the tests themselves passed. Close every connection at teardown.
    yield
    while _OPEN_CONNS:
        conn = _OPEN_CONNS.pop()
        await conn.close()


async def _store() -> MemoryStore:
    import tempfile
    from pathlib import Path

    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    _OPEN_CONNS.append(conn)
    store = MemoryStore(conn, lenses_dir=Path(tempfile.mkdtemp()) / "lenses")
    await store.init_schema()
    return store


async def _service(sessions: dict[str, FakeSession], judge=None, **cfg) -> CaptureService:
    # Every CaptureService gets a real tmp store: close()/sweep() always read a
    # watermark from the meta table, so a None store is never valid.
    return CaptureService(
        raw_sessions=FakeSessions(sessions),
        raw_automations=None,
        store=await _store(),
        cheap_llm=judge,
        config=CaptureConfig(**cfg),
    )


# --- scope assignment -------------------------------------------------------


async def test_scope_bare_chat_is_user_scope():
    s = FakeSession("s1", _msgs("hi"), datetime.now(UTC))
    svc = await _service({"s1": s})
    unit = await svc.close("s1", BoundaryKind.SESSION)
    assert unit is not None
    assert unit.scope.kind is ScopeKind.USER
    assert unit.scope.key is None
    assert unit.role is ExchangeRole.LIVE_CHAT


async def test_scope_project_chat_is_project_scope():
    s = FakeSession("s2", _msgs("hi"), datetime.now(UTC), project_id="proj_abc")
    svc = await _service({"s2": s})
    unit = await svc.close("s2", BoundaryKind.SESSION)
    assert unit.scope.kind is ScopeKind.PROJECT
    assert unit.scope.key == "proj_abc"


async def test_scope_automation_is_session_scope_keyed_by_origin():
    s = FakeSession(
        "s3", _msgs("run"), datetime.now(UTC), session_type="automation",
        origin_automation_id="auto_99",
    )
    svc = await _service({"s3": s})
    unit = await svc.close("s3", BoundaryKind.SESSION)
    assert unit.scope.kind is ScopeKind.SESSION
    assert unit.scope.key == "auto_99"
    assert unit.role is ExchangeRole.AUTOMATION


# --- evidence anchoring -----------------------------------------------------


async def test_exchanges_carry_source_refs_into_raw():
    s = FakeSession("s4", _msgs("alpha", "beta"), datetime.now(UTC))
    svc = await _service({"s4": s})
    unit = await svc.close("s4", BoundaryKind.SESSION)
    assert [e.text for e in unit.exchanges] == ["alpha", "beta"]
    assert unit.source_refs == [e.source_ref for e in unit.exchanges]
    assert all(r.kind == "chat_turn" for r in unit.source_refs)
    assert unit.source_refs[0].ref == "s4:0"
    assert unit.source_refs[1].ref == "s4:1"


async def test_empty_messages_yield_no_unit():
    s = FakeSession("s5", [], datetime.now(UTC))
    svc = await _service({"s5": s})
    assert await svc.close("s5", BoundaryKind.SESSION) is None


async def test_blank_content_is_skipped():
    s = FakeSession("s6", [{"role": "user", "content": "  "}, {"role": "user", "content": "real"}], datetime.now(UTC))
    svc = await _service({"s6": s})
    unit = await svc.close("s6", BoundaryKind.SESSION)
    assert [e.text for e in unit.exchanges] == ["real"]


# --- forced / boundary kinds ------------------------------------------------


async def test_explicit_close_is_forced():
    s = FakeSession("s7", _msgs("x"), datetime.now(UTC))
    svc = await _service({"s7": s})
    unit = await svc.close("s7", BoundaryKind.EXPLICIT)
    assert unit.boundary is BoundaryKind.EXPLICIT
    assert unit.forced is True


async def test_session_close_is_not_forced():
    s = FakeSession("s8", _msgs("x"), datetime.now(UTC))
    svc = await _service({"s8": s})
    unit = await svc.close("s8", BoundaryKind.SESSION)
    assert unit.forced is False


async def test_on_remember_is_forced_single_exchange():
    svc = await _service({})
    ref = SourceRef(kind="chat_turn", ref="run1:tool2")
    scope = Scope(kind=ScopeKind.USER)
    unit = await svc.on_remember("I prefer dark mode", scope, ref)
    assert unit.forced is True
    assert unit.boundary is BoundaryKind.EXPLICIT
    assert len(unit.exchanges) == 1
    assert unit.exchanges[0].text == "I prefer dark mode"
    assert unit.source_refs == [ref]


# --- watermark durability ---------------------------------------------------


async def test_watermark_roundtrip_via_meta_table():
    s = FakeSession("s9", _msgs("one", "two"), datetime.now(UTC))
    svc = await _service({"s9": s})

    unit = await svc.close("s9", BoundaryKind.SESSION)
    assert await svc._read_watermark(unit.watermark.source_id) is None
    await svc.commit_watermark(unit.watermark)
    stored = await svc._read_watermark(unit.watermark.source_id)
    assert stored is not None
    assert stored.cursor == unit.watermark.cursor == "s9:1"


async def test_close_after_committed_watermark_is_idempotent_on_no_new():
    s = FakeSession("s10", _msgs("a", "b"), datetime.now(UTC))
    svc = await _service({"s10": s})

    unit = await svc.close("s10", BoundaryKind.SESSION)
    await svc.commit_watermark(unit.watermark)
    # No new exchanges past the cursor → nothing to bound.
    assert await svc.close("s10", BoundaryKind.SESSION) is None


async def test_close_only_includes_exchanges_past_cursor():
    s = FakeSession("s11", _msgs("a", "b"), datetime.now(UTC))
    svc = await _service({"s11": s})
    first = await svc.close("s11", BoundaryKind.SESSION)
    await svc.commit_watermark(first.watermark)

    # New activity arrives.
    s.messages = _msgs("a", "b", "c", "d")
    second = await svc.close("s11", BoundaryKind.SESSION)
    assert [e.text for e in second.exchanges] == ["c", "d"]
    assert second.watermark.cursor == "s11:3"


# --- background sweep: CAP --------------------------------------------------


async def test_sweep_cap_force_cuts_runaway_open_stream():
    texts = [f"step {i}" for i in range(7)]
    # Open stream: very recent activity (not idle).
    s = FakeSession("s12", _msgs(*texts), datetime.now(UTC))
    svc = await _service({"s12": s}, max_window_exchanges=3)

    units = await svc.sweep("session:s12")
    # 7 exchanges, cap=3 → two CAP units of 3, remainder (1) stays pending
    # because the stream is open (not closed/idle).
    assert [u.boundary for u in units] == [BoundaryKind.CAP, BoundaryKind.CAP]
    assert [len(u.exchanges) for u in units] == [3, 3]


async def test_sweep_emits_remainder_only_when_session_closed():
    texts = [f"s{i}" for i in range(4)]
    idle = datetime.now(UTC) - timedelta(hours=2)
    s = FakeSession("s13", _msgs(*texts), idle)
    svc = await _service({"s13": s}, max_window_exchanges=10, idle_seconds=60)

    units = await svc.sweep("session:s13")
    assert len(units) == 1
    assert units[0].boundary is BoundaryKind.SESSION
    assert len(units[0].exchanges) == 4


async def test_sweep_open_stream_no_boundary_emits_nothing():
    s = FakeSession("s14", _msgs("a", "b"), datetime.now(UTC))
    svc = await _service({"s14": s}, max_window_exchanges=10)
    # Open stream, no cap, no judge → nothing to safely bound yet.
    assert await svc.sweep("session:s14") == []


# --- background sweep: SEMANTIC ---------------------------------------------


async def test_sweep_semantic_cut_uses_judge():
    s = FakeSession("s15", _msgs("topicA-1", "topicA-2", "topicB-1", "topicB-2"), datetime.now(UTC))
    judge = FakeJudge(SemanticBoundary(shift=True, cut_after_index=1, reason="A→B"))
    svc = await _service({"s15": s}, judge=judge, max_window_exchanges=100)

    units = await svc.sweep("session:s15")
    assert judge.calls >= 1
    assert units[0].boundary is BoundaryKind.SEMANTIC
    assert [e.text for e in units[0].exchanges] == ["topicA-1", "topicA-2"]


async def test_semantic_out_of_range_cut_is_ignored():
    s = FakeSession("s16", _msgs("a", "b", "c"), datetime.now(UTC))
    # cut at final index segments nothing → must be ignored (drop-on-doubt).
    judge = FakeJudge(SemanticBoundary(shift=True, cut_after_index=2, reason="bad"))
    svc = await _service({"s16": s}, judge=judge, max_window_exchanges=100)
    assert await svc.sweep("session:s16") == []


async def test_semantic_judge_failure_degrades_to_no_cut():
    s = FakeSession("s17", _msgs("a", "b"), datetime.now(UTC))
    judge = FakeJudge(None)  # raises
    svc = await _service({"s17": s}, judge=judge, max_window_exchanges=100)
    assert await svc.sweep("session:s17") == []


async def test_hot_path_close_makes_zero_llm_calls():
    s = FakeSession("s18", _msgs("a", "b"), datetime.now(UTC))
    judge = FakeJudge(SemanticBoundary(shift=True, cut_after_index=0, reason="x"))
    svc = await _service({"s18": s}, judge=judge)
    await svc.close("s18", BoundaryKind.SESSION)
    assert judge.calls == 0


async def test_sweep_unsupported_source_id_raises():
    svc = await _service({})
    with pytest.raises(ValueError):
        await svc.sweep("automation:abc")
