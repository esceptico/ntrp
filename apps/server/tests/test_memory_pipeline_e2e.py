"""End-to-end integration test for the assembled MemoryPipeline.

In-memory tmp DB ONLY (never ~/.ntrp/memory.db). The LLM and embedder are
stubbed so the FULL ingest path (capture unit -> admit -> extract -> reconcile),
the read path (retrieve), the remember() WriteSeam, and the background
consolidate loop are exercised deterministically with zero network.

This proves the wiring in ntrp/memory/pipeline/runtime.py: the components
compose, watermarks advance, a claim minted via ingest is recallable, and the
remember() seam shares the same admit->write path.
"""

import hashlib

import aiosqlite
import numpy as np
import pytest
import pytest_asyncio

from ntrp.agent.types.llm import Choice, CompletionResponse, FinishReason, Message, Role
from ntrp.agent.types.usage import Usage
from ntrp.memory.models import Provenance, Scope, ScopeKind, SourceRef, Status
from ntrp.memory.pipeline.prompts import AdmitDecision
from ntrp.memory.pipeline.prompts_extract import ExtractedClaim, ExtractOutput
from ntrp.memory.pipeline.prompts_reconcile import (
    BatchReconcile,
    ReconcileRow,
    SubjectResolution,
)
from ntrp.memory.pipeline.runtime import MemoryPipeline, MemoryPipelineConfig
from ntrp.memory.pipeline.types import BoundaryKind, CaptureUnit, ExchangeRole, RawExchange, Retrieval, Watermark
from ntrp.memory.store import MemoryStore

pytestmark = pytest.mark.asyncio

USER_SCOPE = Scope(kind=ScopeKind.USER)


def _response(payload_json: str) -> CompletionResponse:
    msg = Message(role=Role.ASSISTANT, content=payload_json, tool_calls=None, reasoning_content=None)
    return CompletionResponse(
        choices=[Choice(message=msg, finish_reason=FinishReason.STOP)],
        usage=Usage(),
        model="stub",
    )


class StubLLM:
    """Routes by response_format; returns scripted structured outputs.

    Defaults model the common path: ADMIT everything, extract one claim about
    Timur, resolve a NEW canonical subject, ADD the claim. Tests can override the
    queues for other branches.
    """

    def __init__(self):
        self.admit = AdmitDecision(
            predictable_from_memory=False, surprising_residual="dark mode", reason="new"
        )
        self.extract = ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="Timur prefers dark mode",
                    source_turn_id="s1:0",
                    provenance="recorded",
                    canonical_subject="Timur",
                    subject_surfaces=["I", "me", "Timur"],
                    grounded=True,
                )
            ]
        )
        self.subject = SubjectResolution(decision="NEW", canonical_subject="Timur", reason="new")
        self.batch = BatchReconcile(rows=[ReconcileRow(claim_index=0, op="add")])
        self.calls = {"admit": 0, "extract": 0, "subject": 0, "batch": 0}

    async def completion(self, *, response_format=None, **kwargs) -> CompletionResponse:
        if response_format is AdmitDecision:
            self.calls["admit"] += 1
            return _response(self.admit.model_dump_json())
        if response_format is ExtractOutput:
            self.calls["extract"] += 1
            return _response(self.extract.model_dump_json())
        if response_format is SubjectResolution:
            self.calls["subject"] += 1
            return _response(self.subject.model_dump_json())
        if response_format is BatchReconcile:
            self.calls["batch"] += 1
            return _response(self.batch.model_dump_json())
        raise AssertionError(f"unexpected response_format {response_format}")


class StubEmbedder:
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


class FakeSession:
    def __init__(self, session_id, messages, last_activity):
        self.session_id = session_id
        self.messages = messages
        self.last_activity = last_activity
        self.session_type = "chat"
        self.origin_automation_id = None
        self.project_id = None


class FakeSessions:
    def __init__(self, sessions):
        self._sessions = sessions

    async def load_session(self, session_id):
        return self._sessions.get(session_id)


@pytest_asyncio.fixture
async def store(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await s.init_schema()
    yield s
    await conn.close()


def _pipeline(store, llm, sessions=None) -> MemoryPipeline:
    return MemoryPipeline(
        store=store,
        embed=StubEmbedder(),
        cheap_llm=llm,
        strong_llm=llm,
        raw_sessions=FakeSessions(sessions or {}),
        raw_automations=None,
        config=MemoryPipelineConfig(
            cheap_model="cheap", strong_model="strong", consolidation_interval=30
        ),
        eligible_scopes=lambda: [USER_SCOPE],
    )


def _unit(text="I prefer dark mode") -> CaptureUnit:
    ref = SourceRef(kind="chat_turn", ref="s1:0")
    exch = RawExchange(turn_id="s1:0", text=text, source_ref=ref)
    return CaptureUnit(
        scope=USER_SCOPE,
        role=ExchangeRole.LIVE_CHAT,
        exchanges=[exch],
        source_refs=[ref],
        boundary=BoundaryKind.SESSION,
        watermark=Watermark(source_id="session:s1", cursor="s1:0", swept_at="2026-06-01T00:00:00+00:00"),
    )


# --- ingest: capture -> admit -> extract -> reconcile ----------------


async def test_ingest_unit_resolves_subject_and_adds_claim(store):
    llm = StubLLM()
    pipe = _pipeline(store, llm)

    results = await pipe.ingest_unit(_unit())

    assert len(results) == 1
    assert results[0].op.value == "add"
    # The claim was written, is the lone active claim in USER scope, and carries
    # its subject as an attribute (no entity row).
    claims = await store.query(scope=USER_SCOPE, status=Status.ACTIVE, limit=10)
    assert len(claims) == 1
    assert "dark mode" in claims[0].content.lower()
    assert claims[0].canonical_subject == "Timur"
    # Reconcile mints NO lens rows: lenses are a separate view layer, never
    # written by ingest.
    lenses = await store.list_lenses(scope=USER_SCOPE)
    assert lenses == []
    # admit + extract each fire once. Reconcile makes ZERO judge calls here: the
    # subject recall set is empty (no prior claims) -> categorical NEW (no subject
    # call), and a brand-new subject has no prior claims -> all-ADD (no batch
    # call). This is the documented heuristic-free fast path, not a skipped stage.
    assert llm.calls == {"admit": 1, "extract": 1, "subject": 0, "batch": 0}


async def test_ingest_advances_watermark(store):
    llm = StubLLM()
    pipe = _pipeline(store, llm)
    unit = _unit()

    assert await pipe.capture._read_watermark("session:s1") is None
    await pipe.ingest_unit(unit)
    wm = await pipe.capture._read_watermark("session:s1")
    assert wm is not None and wm.cursor == "s1:0"


async def test_rejected_unit_writes_nothing_but_advances(store):
    llm = StubLLM()
    llm.admit = AdmitDecision(predictable_from_memory=True, surprising_residual="", reason="known")
    pipe = _pipeline(store, llm)

    results = await pipe.ingest_unit(_unit())
    assert results == []
    claims = await store.query(scope=USER_SCOPE, status=Status.ACTIVE, limit=10)
    assert claims == []
    # Rejected but processed -> watermark advanced so it is not re-swept.
    wm = await pipe.capture._read_watermark("session:s1")
    assert wm is not None


# --- read: retrieve --------------------------------------------------


async def test_retrieve_recalls_an_ingested_claim(store):
    llm = StubLLM()
    pipe = _pipeline(store, llm)
    await pipe.ingest_unit(_unit())

    ctx = await pipe.retrieve(Retrieval(goal="what mode does the user prefer", scope=USER_SCOPE))
    assert ctx.items, ctx.diagnostics
    assert any("dark mode" in r.item.content.lower() for r in ctx.items)


async def test_retrieve_empty_scope_returns_nothing(store):
    pipe = _pipeline(store, StubLLM())
    ctx = await pipe.retrieve(Retrieval(goal="anything", scope=USER_SCOPE))
    assert ctx.items == []
    assert ctx.rendered == ""


# --- close_session: capture from raw + ingest ------------------------


async def test_close_session_ingests_from_raw(store):
    from datetime import UTC, datetime

    sessions = {
        "s1": FakeSession("s1", [{"role": "user", "content": "I prefer dark mode"}], datetime.now(UTC))
    }
    llm = StubLLM()
    pipe = _pipeline(store, llm, sessions=sessions)

    results = await pipe.close_session("s1", BoundaryKind.SESSION)
    assert len(results) == 1
    claims = await store.query(scope=USER_SCOPE, status=Status.ACTIVE, limit=10)
    assert len(claims) == 1


# --- remember(): the WriteSeam shares the admit->write path ----------


async def test_remember_seam_adds_a_user_authored_claim(store):
    from ntrp.memory.pipeline.write import WriteRequest

    llm = StubLLM()
    # remember() is forced (bypass_admit): admit short-circuits to ADMIT, then the
    # seam runs the SAME extract->reconcile path as every other ingest (vision
    # §1.7). Extract is what resolves the canonical subject — the seam no longer
    # dumps raw content as the subject. The extracted claim must be grounded in the
    # remember unit's synthetic turn id ("w0").
    llm.extract = ExtractOutput(
        claims=[
            ExtractedClaim(
                content="Timur lives in Berlin",
                source_turn_id="w0",
                provenance="user_authored",
                canonical_subject="Timur",
                subject_surfaces=["I", "Timur"],
                grounded=True,
            )
        ]
    )
    pipe = _pipeline(store, llm)

    outcome = await pipe.write_seam.admit_and_write(
        WriteRequest(
            content="Timur lives in Berlin",
            scope=USER_SCOPE,
            provenance=Provenance.USER_AUTHORED,
            source_refs=[SourceRef(kind="chat_turn", ref="run1:tool2")],
            bypass_admit=True,
        )
    )

    assert outcome.written is True
    assert outcome.item_id is not None
    assert llm.calls["extract"] == 1  # the seam ran Extract, not a content shortcut
    claims = await store.query(scope=USER_SCOPE, status=Status.ACTIVE, limit=10)
    assert any("Berlin" in c.content for c in claims)
    # subject was RESOLVED by extract, not set to the raw sentence
    berlin = next(c for c in claims if "Berlin" in c.content)
    assert berlin.canonical_subject == "Timur"
    assert berlin.provenance is Provenance.USER_AUTHORED


# --- background consolidate loop is constructible + runs one sweep ---


async def test_consolidate_run_once_is_safe_on_empty_scope(store):
    pipe = _pipeline(store, StubLLM())
    report = await pipe.consolidate.run_once(scope=USER_SCOPE)
    assert report.merged == 0 and report.invalidated == 0


# --- full KnowledgeRuntime boot wires the pipeline (tmp dir, no network) ---


async def test_knowledge_runtime_boots_memory_pipeline(tmp_path, monkeypatch):
    import ntrp.llm.models as llm_models
    from ntrp.config import Config
    from ntrp.llm.models import EmbeddingModel, Provider
    from ntrp.llm.router import init as llm_init
    from ntrp.memory.pipeline.write import WriteSeam
    from ntrp.server.runtime.knowledge import KnowledgeRuntime
    from ntrp.server.stores import Stores
    from ntrp.tools.memory import MEMORY_WRITE_SERVICE

    monkeypatch.setitem(
        llm_models._embedding_models,
        "test-embedding",
        EmbeddingModel("test-embedding", Provider.OPENAI, 8),
    )

    config = Config(
        ntrp_dir=tmp_path,
        memory=True,
        embedding_model="test-embedding",
        chat_model="claude-haiku-4-5",
        memory_model="claude-haiku-4-5",
    )
    config.db_dir.mkdir(parents=True, exist_ok=True)
    llm_init(config)

    stores = await Stores.connect(config)
    knowledge = KnowledgeRuntime(config)
    try:
        await knowledge.connect(stores)

        # The pipeline wired up over the tmp memory db (NEVER ~/.ntrp/memory.db).
        assert knowledge.memory_ready is True
        assert (tmp_path / "memory.db").exists()
        assert isinstance(knowledge.memory_service, WriteSeam)
        assert knowledge.memory_retrieval is not None

        # WIRING CONTRACT: `memory_retrieval` is the whole MemoryPipeline, NOT
        # the bare Retriever. routers/memory.py reads the lens VIEW surface off
        # this same handle (.lens_registry / .lens_projector / .lens_writeback —
        # see routers/memory.py:249,274,448,468) alongside the read egress
        # `.retrieve()`. A Retriever exposes only `.retrieve`, so collapsing this
        # to `pipeline.retriever` would AttributeError every lens endpoint at
        # runtime while leaving the suite green. Pin both surfaces here.
        assert knowledge.memory_retrieval is knowledge._memory_pipeline
        assert callable(knowledge.memory_retrieval.retrieve)
        for view_attr in ("lens_registry", "lens_projector", "lens_writeback"):
            assert hasattr(knowledge.memory_retrieval, view_attr), view_attr

        # The remember() permission service is exposed so the tool un-hides.
        assert MEMORY_WRITE_SERVICE in knowledge.tool_services()
    finally:
        await knowledge.stop()
        await knowledge.close()
        await stores.close()
