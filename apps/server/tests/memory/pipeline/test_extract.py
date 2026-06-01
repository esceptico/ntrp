"""Unit tests for the Extract stage (CONTRACTS §6).

Extract has NO store dependency, so these tests use a fake CompletionClient and
touch no database whatsoever. No real LLM calls (cost-bounded).

The extractor emits the LLM-resolved subject (canonical_subject) plus the observed
surfaces (subject_surfaces); there is no proper-noun regex or stopword set. The
only guards are categorical: empty content, unresolvable turn id, model-flagged
ungrounded, and empty canonical_subject (subject_unresolved).
"""

from dataclasses import dataclass

import pytest

from ntrp.memory.models import Provenance, Scope, ScopeKind, SourceRef
from ntrp.memory.pipeline.extract import Extractor
from ntrp.memory.pipeline.prompts_extract import ExtractedClaim, ExtractOutput
from ntrp.memory.pipeline.types import (
    AdmitResult,
    BoundaryKind,
    CaptureUnit,
    ExchangeRole,
    RawExchange,
    Verdict,
    Watermark,
)


# --- minimal CompletionResponse shape (ntrp.agent.types.llm) ---------
@dataclass
class _Msg:
    content: str | None


@dataclass
class _Choice:
    message: _Msg


@dataclass
class _Resp:
    choices: list[_Choice]


class FakeLLM:
    """Mirrors CompletionClient.completion; returns a JSON-string response."""

    def __init__(self, output: ExtractOutput | None = None, *, raise_exc: bool = False):
        self._output = output if output is not None else ExtractOutput(claims=[])
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def completion(self, **kwargs):
        self.calls.append(kwargs)
        if self._raise:
            raise RuntimeError("llm down")
        return _Resp(choices=[_Choice(message=_Msg(content=self._output.model_dump_json()))])


def _user_scope() -> Scope:
    return Scope(kind=ScopeKind.USER)


def _source_ref(ref: str) -> SourceRef:
    return SourceRef(kind="chat_turn", ref=ref, captured_at="2026-06-01T00:00:00Z")


def _ex(turn_id: str, text: str) -> RawExchange:
    return RawExchange(turn_id=turn_id, text=text, source_ref=_source_ref(turn_id))


def _unit(exchanges: list[RawExchange], *, scope: Scope | None = None) -> CaptureUnit:
    scope = scope or _user_scope()
    return CaptureUnit(
        scope=scope,
        role=ExchangeRole.LIVE_CHAT,
        exchanges=exchanges,
        source_refs=[ex.source_ref for ex in exchanges],
        boundary=BoundaryKind.SESSION,
        watermark=Watermark(source_id="s1", cursor="0", swept_at="2026-06-01T00:00:00Z"),
    )


def _admitted(
    exchanges: list[RawExchange],
    *,
    verdict: Verdict = Verdict.ADMIT,
    residual: str | None = "something new",
    scope: Scope | None = None,
) -> AdmitResult:
    return AdmitResult(
        verdict=verdict,
        unit=_unit(exchanges, scope=scope),
        residual=residual if verdict is Verdict.ADMIT else None,
        reason="test",
        candidates=[],
        forced=False,
    )


async def _run(llm: FakeLLM, admitted: AdmitResult):
    return await Extractor(llm).extract(admitted, model="cheap-model")


# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_emits_grounded_claim_with_canonical_subject():
    ex = _ex("t1", "I prefer dark mode in my editor.")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="User prefers dark mode in their editor.",
                    source_turn_id="t1",
                    provenance="user_authored",
                    canonical_subject="the user",
                    subject_surfaces=["I", "my"],
                    grounded=True,
                )
            ]
        )
    )
    res = await _run(llm, _admitted([ex]))

    assert len(llm.calls) == 1  # exactly one cheap call
    assert llm.calls[0]["model"] == "cheap-model"
    assert llm.calls[0]["response_format"] is ExtractOutput
    assert len(res.candidates) == 1
    assert res.dropped == []
    c = res.candidates[0]
    assert c.content == "User prefers dark mode in their editor."
    assert c.provenance is Provenance.USER_AUTHORED
    assert c.canonical_subject == "the user"
    assert c.subject_surfaces == ["I", "my"]
    assert c.scope == _user_scope()
    assert c.source_refs == [ex.source_ref]


@pytest.mark.asyncio
async def test_reject_short_circuits_without_llm_call():
    ex = _ex("t1", "anything")
    llm = FakeLLM(ExtractOutput(claims=[]))
    res = await _run(llm, _admitted([ex], verdict=Verdict.REJECT))
    assert llm.calls == []  # zero calls — pipeline stopped at Admit
    assert res.candidates == []
    assert res.dropped == []


@pytest.mark.asyncio
async def test_guard_unresolvable_turn_id_drops_with_evidence_missing():
    ex = _ex("t1", "real turn text")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="A claim citing a turn that does not exist.",
                    source_turn_id="t999",
                    provenance="recorded",
                    canonical_subject="the project",
                    grounded=True,
                )
            ]
        )
    )
    res = await _run(llm, _admitted([ex]))
    assert res.candidates == []
    assert len(res.dropped) == 1
    assert res.dropped[0].reason == "evidence_missing"
    assert res.dropped[0].turn_id == "t999"


@pytest.mark.asyncio
async def test_guard_grounded_false_drops():
    ex = _ex("t1", "He left.")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="Bob left the building.",
                    source_turn_id="t1",
                    provenance="inferred",
                    canonical_subject="Bob",
                    grounded=False,
                )
            ]
        )
    )
    res = await _run(llm, _admitted([ex]))
    assert res.candidates == []
    assert len(res.dropped) == 1
    assert res.dropped[0].reason == "grounded_false"


@pytest.mark.asyncio
async def test_guard_empty_canonical_subject_drops_subject_unresolved():
    ex = _ex("t1", "The user scheduled a meeting for next week.")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="A meeting is scheduled for next week.",
                    source_turn_id="t1",
                    provenance="recorded",
                    canonical_subject="   ",
                    grounded=True,
                )
            ]
        )
    )
    res = await _run(llm, _admitted([ex]))
    assert res.candidates == []
    assert len(res.dropped) == 1
    assert res.dropped[0].reason == "subject_unresolved"


@pytest.mark.asyncio
async def test_resolved_subject_passes_through():
    ex = _ex("t1", "Timur uses Postgres for the analytics service.")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="Timur uses Postgres for the analytics service.",
                    source_turn_id="t1",
                    provenance="recorded",
                    canonical_subject="Timur",
                    subject_surfaces=["Timur"],
                    grounded=True,
                )
            ]
        )
    )
    res = await _run(llm, _admitted([ex]))
    assert len(res.candidates) == 1
    assert res.dropped == []
    assert res.candidates[0].canonical_subject == "Timur"


@pytest.mark.asyncio
async def test_unknown_provenance_falls_back_to_recorded():
    ex = _ex("t1", "The build passed.")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="The build passed.",
                    source_turn_id="t1",
                    provenance="banana",
                    canonical_subject="the build",
                    grounded=True,
                )
            ]
        )
    )
    res = await _run(llm, _admitted([ex]))
    assert len(res.candidates) == 1
    assert res.candidates[0].provenance is Provenance.RECORDED


@pytest.mark.asyncio
async def test_multiple_turns_each_claim_grounds_to_its_own_source_ref():
    e1 = _ex("t1", "I live in Berlin.")
    e2 = _ex("t2", "My favorite language is Python.")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="User lives in Berlin.",
                    source_turn_id="t1",
                    provenance="user_authored",
                    canonical_subject="the user",
                    grounded=True,
                ),
                ExtractedClaim(
                    content="User's favorite language is Python.",
                    source_turn_id="t2",
                    provenance="user_authored",
                    canonical_subject="the user",
                    grounded=True,
                ),
            ]
        )
    )
    res = await _run(llm, _admitted([e1, e2]))
    assert len(res.candidates) == 2
    assert res.candidates[0].source_refs == [e1.source_ref]
    assert res.candidates[1].source_refs == [e2.source_ref]


@pytest.mark.asyncio
async def test_llm_failure_yields_empty_not_crash():
    ex = _ex("t1", "anything")
    llm = FakeLLM(raise_exc=True)
    res = await _run(llm, _admitted([ex]))
    assert len(llm.calls) == 1
    assert res.candidates == []
    assert res.dropped == []


@pytest.mark.asyncio
async def test_empty_content_claim_is_skipped_silently():
    ex = _ex("t1", "noise")
    llm = FakeLLM(
        ExtractOutput(
            claims=[
                ExtractedClaim(
                    content="   ",
                    source_turn_id="t1",
                    provenance="recorded",
                    canonical_subject="the build",
                    grounded=True,
                )
            ]
        )
    )
    res = await _run(llm, _admitted([ex]))
    assert res.candidates == []
    assert res.dropped == []


@pytest.mark.asyncio
async def test_prompt_includes_turn_ids_and_residual_and_system_rubric():
    ex = _ex("t1", "I prefer tabs over spaces.")
    llm = FakeLLM(ExtractOutput(claims=[]))
    await _run(llm, _admitted([ex], residual="user formatting preference"))
    messages = llm.calls[0]["messages"]
    system_msg = messages[0]["content"]
    user_msg = messages[-1]["content"]
    assert messages[0]["role"] == "system"
    assert "atomic" in system_msg.lower()
    assert "turn_id=t1" in user_msg
    assert "user formatting preference" in user_msg
    # The rubric must instruct the model to emit a resolved, non-pronoun subject —
    # identity recall keys on canonical_subject, so it can never be a bare pronoun.
    assert "canonical_subject" in system_msg
