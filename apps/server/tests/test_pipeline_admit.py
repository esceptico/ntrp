"""Unit tests for the Admit gate (CONTRACTS §5).

Temp-file SQLite store only -- never the real ~/.ntrp/memory.db. The cheap LLM
and embedder are fakes so no network/model is touched and we can assert the
exact-one-call cost ceiling.
"""

from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.agent.types.llm import Choice, CompletionResponse, FinishReason, Message, Role
from ntrp.agent.types.usage import Usage
from ntrp.memory import (
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    SourceRef,
)
from ntrp.memory.pipeline.admit import AdmitGate
from ntrp.memory.pipeline.prompts import AdmitDecision
from ntrp.memory.pipeline.types import (
    BoundaryKind,
    CaptureUnit,
    ExchangeRole,
    RawExchange,
    Verdict,
    Watermark,
)
from ntrp.memory.store import MemoryStore

pytestmark = pytest.mark.asyncio

_MODEL = "test-cheap"


# --- fakes -----------------------------------------------------------


class FakeLLM:
    """Records every call and returns a queued AdmitDecision (or raises)."""

    def __init__(self, decision: AdmitDecision | None = None, raise_exc: bool = False):
        self.decision = decision
        self.raise_exc = raise_exc
        self.calls: list[list[dict]] = []

    async def completion(self, *, messages, model, response_format=None, **kwargs):
        self.calls.append(messages)
        if self.raise_exc:
            raise RuntimeError("model down")
        message = Message(
            role=Role.ASSISTANT,
            content=self.decision.model_dump_json(),
            tool_calls=None,
            reasoning_content=None,
        )
        return CompletionResponse(
            choices=[Choice(message=message, finish_reason=FinishReason.STOP)],
            usage=Usage(),
            model=model,
        )


class FakeEmbedder:
    async def embed_one(self, text):
        return [0.0]

    async def embed(self, texts):
        return [[0.0] for _ in texts]


# --- fixtures --------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db")
    s = MemoryStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


USER_SCOPE = Scope(kind=ScopeKind.USER)


def _unit(text, *, role=ExchangeRole.LIVE_CHAT, forced=False, scope=USER_SCOPE):
    ref = SourceRef(kind="chat_turn", ref="t1")
    return CaptureUnit(
        scope=scope,
        role=role,
        exchanges=[RawExchange(turn_id="t1", text=text, source_ref=ref)],
        source_refs=[ref],
        boundary=BoundaryKind.SESSION,
        watermark=Watermark(source_id="s1", cursor="0", swept_at="2026-06-01T00:00:00+00:00"),
        forced=forced,
    )


async def _seed_claim(store, content, *, scope=USER_SCOPE, id="c1", subject="Timur"):
    item = MemoryItem(
        id=id,
        content=content,
        canonical_subject=subject,
        scope=scope,
        provenance=Provenance.RECORDED,
        source_refs=[SourceRef(kind="chat_turn", ref="seed")],
    )
    await store.create_item(item)
    return item


def _gate(store, llm):
    return AdmitGate(store, llm, FakeEmbedder(), model=_MODEL)


# --- tests -----------------------------------------------------------


async def test_forced_short_circuits_to_admit_without_a_call(store):
    llm = FakeLLM()  # no decision queued; would crash if a call were made
    gate = _gate(store, llm)
    unit = _unit("The user says remember this important fact.", forced=True)

    result = await gate.admit(unit)

    assert result.verdict is Verdict.ADMIT
    assert result.forced is True
    assert result.residual is not None
    assert llm.calls == []  # zero judgment calls on the forced path


async def test_free_reject_below_length_floor(store):
    gate = _gate(store, FakeLLM())

    result = await gate.admit(_unit("ok"))

    assert result.verdict is Verdict.REJECT
    assert "length floor" in result.reason
    assert result.residual is None


async def test_tool_status_rejected_by_judge_not_a_keyword_list(store):
    # Tool-status chatter is NOT free-rejected by a content keyword/prefix list
    # (that pattern is banned). It flows to the judge, which rejects it as
    # carrying nothing memory doesn't already imply.
    llm = FakeLLM(
        AdmitDecision(
            predictable_from_memory=True,
            surprising_residual="",
            reason="pure tool output; nothing to remember",
        )
    )
    gate = _gate(store, llm)

    result = await gate.admit(_unit("exit code 0\nstdout: 12 14 16"))

    assert result.verdict is Verdict.REJECT
    assert len(llm.calls) == 1  # reached the judge — not a free keyword reject


async def test_admit_when_novel_costs_exactly_one_call(store):
    await _seed_claim(store, "Timur prefers tea over coffee.")
    llm = FakeLLM(
        AdmitDecision(
            predictable_from_memory=False,
            surprising_residual="Timur started running marathons",
            reason="new durable fact",
        )
    )
    gate = _gate(store, llm)

    result = await gate.admit(_unit("Timur just signed up for his first marathon."))

    assert result.verdict is Verdict.ADMIT
    assert result.residual == "Timur started running marathons"
    assert len(llm.calls) == 1  # the exact cost ceiling


async def test_reject_when_predictable_from_memory(store):
    await _seed_claim(store, "Timur prefers tea over coffee.")
    llm = FakeLLM(
        AdmitDecision(predictable_from_memory=True, surprising_residual="", reason="already known")
    )
    gate = _gate(store, llm)

    result = await gate.admit(_unit("Timur once again chose tea instead of coffee."))

    assert result.verdict is Verdict.REJECT
    assert result.residual is None
    assert len(llm.calls) == 1


async def test_recall_is_scope_correct(store):
    # Same content in two scopes; recall for the user-scope unit must only surface
    # the user-scope claim (search() is not scope-filtered; the gate intersects).
    await _seed_claim(store, "Project alpha ships on Friday.", scope=USER_SCOPE, id="u1")
    proj = Scope(kind=ScopeKind.PROJECT, key="alpha")
    await _seed_claim(store, "Project alpha ships on Friday.", scope=proj, id="p1")

    llm = FakeLLM(
        AdmitDecision(predictable_from_memory=True, surprising_residual="", reason="known")
    )
    gate = _gate(store, llm)

    result = await gate.admit(_unit("alpha ships Friday this week", scope=USER_SCOPE))

    recalled_ids = {c.id for c in result.candidates}
    assert "u1" in recalled_ids
    assert "p1" not in recalled_ids


async def test_recalled_candidates_are_shown_to_the_judge(store):
    await _seed_claim(store, "Timur prefers raw SQL over ORMs.")
    llm = FakeLLM(
        AdmitDecision(predictable_from_memory=True, surprising_residual="", reason="known")
    )
    gate = _gate(store, llm)

    await gate.admit(_unit("Timur said he likes raw SQL queries."))

    user_msg = llm.calls[0][1]["content"]
    assert "raw SQL over ORMs" in user_msg  # the incumbent claim was put beside the exchange


async def test_judge_failure_biases_to_admit(store):
    llm = FakeLLM(raise_exc=True)
    gate = _gate(store, llm)

    result = await gate.admit(_unit("Some genuinely ambiguous new statement here."))

    assert result.verdict is Verdict.ADMIT
    assert "biased ADMIT" in result.reason
    assert len(llm.calls) == 1  # the call was attempted exactly once


async def test_automation_role_strengthens_system_prompt(store):
    llm = FakeLLM(
        AdmitDecision(predictable_from_memory=True, surprising_residual="", reason="run mechanics")
    )
    gate = _gate(store, llm)

    await gate.admit(
        _unit("The scheduled job fetched 4 records and finished.", role=ExchangeRole.AUTOMATION)
    )

    system_msg = llm.calls[0][0]["content"]
    assert "AUTOMATION run" in system_msg


async def test_fts_unavailable_biases_predictable_to_admit(store):
    await _seed_claim(store, "Timur prefers tea over coffee.")
    store._has_fts = False  # simulate FTS5 unavailable
    llm = FakeLLM(
        AdmitDecision(predictable_from_memory=True, surprising_residual="", reason="thin context")
    )
    gate = _gate(store, llm)

    result = await gate.admit(_unit("Timur drinks tea in the mornings."))

    # FTS down -> judged on thin scoped pool -> false-reject not tolerated.
    assert result.verdict is Verdict.ADMIT
    assert len(llm.calls) == 1


async def test_fts_unavailable_recall_uses_scoped_query_only(store):
    await _seed_claim(store, "Timur prefers tea.", id="x1")
    store._has_fts = False
    llm = FakeLLM(
        AdmitDecision(predictable_from_memory=False, surprising_residual="r", reason="ok")
    )
    gate = _gate(store, llm)

    result = await gate.admit(_unit("Something new and unrelated to tea entirely."))

    # With FTS down, recall falls back to the scoped active pool.
    assert "x1" in {c.id for c in result.candidates}


async def test_has_fts_property_reflects_private_flag(store):
    assert store.has_fts is True
    store._has_fts = False
    assert store.has_fts is False
