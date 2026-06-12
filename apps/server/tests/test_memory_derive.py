"""The DREAM — recursive derivation (Derivation — spec.md; consolidate.py §3–4 +
records.py justifications/standing/nogoods).

Hermetic: a real tmp RecordStore (FTS-only) + the scripted StubLLM pattern. The
sweep's call order per run_once: one LintOps judge per neighborhood -> (label
hygiene if >=2 labels) -> one RejudgeOp per unresolved derivation -> one
DreamOps per neighborhood -> one VerifyVerdict per surviving candidate.

Covers the spec's traceability table:
  (a) derive commits with citation: provenance=derived, depth, justification;
  (b) cite-or-void: hallucinated premise ids are dropped;
  (c) verify-before-commit rejection stores NOTHING;
  (d) duplicate conclusion lands as an extra JUSTIFICATION (corroboration);
  (e) premise death -> dependent unresolved -> excluded from search;
  (f) JTMS: a second living justification keeps the dependent active;
  (g) re-judgment: REAFFIRM (re-activates), REVISE (supersedes into corrected),
      RETIRE (+ nogood, fed into later dream prompts);
  (h) depth cap; (i) cycle guard; (j) recursion: derived records are premises.
"""

import json
from pathlib import Path

import pytest

from ntrp.memory.consolidate import Consolidate
from ntrp.memory.models import Provenance, Standing
from ntrp.memory.prompts_consolidate import LintOps
from ntrp.memory.records import RecordStore
from tests.conftest import completion_response

pytestmark = pytest.mark.asyncio

_NOP = LintOps().model_dump_json()  # parses as empty DreamOps/LintOps alike


class StubLLM:
    def __init__(self, *responses: str):
        self._queue = list(responses)
        self.calls: list[dict] = []

    async def completion(self, *, messages, model, reasoning_effort=None, response_format=None, **kwargs):
        self.calls.append({"messages": messages, "response_format": response_format})
        body = self._queue.pop(0) if self._queue else _NOP
        return completion_response(body)


def _consolidate(tmp_path: Path, records: RecordStore, llm) -> Consolidate:
    return Consolidate(records, llm, model="memory-model", db_path=tmp_path / "memory.db")


def _dream(question: str, conclusion: str, premise_ids: list[str], mode: str = "deduction") -> str:
    return json.dumps({"candidates": [{
        "question": question, "conclusion": conclusion,
        "premise_ids": premise_ids, "mode": mode,
    }]})


def _verify(supported: bool = True, nontrivial: bool = True, duplicate_of: str | None = None) -> str:
    return json.dumps({"supported": supported, "nontrivial": nontrivial, "duplicate_of": duplicate_of})


def _rejudge(op: str, text: str | None = None, premise_ids: list[str] | None = None, why: str = "") -> str:
    return json.dumps({"op": op, "text": text, "premise_ids": premise_ids or [], "why": why})


# --- (a) derive commits with citation ------------------------------------------


async def test_dream_derives_a_cited_conclusion(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user cycles to work every morning")
    b = await records.add("the user injured a leg and cycles nowhere for a month")
    llm = StubLLM(
        _NOP,  # neighborhood lint judge
        _dream("how does the user commute now?",
               "the user cannot commute by bicycle while the leg heals",
               [a.id, b.id], mode="deduction"),
        _verify(),
    )
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.derived == 1
    derived = [r for r in await records.list() if r.provenance == Provenance.DERIVED]
    assert len(derived) == 1
    d = derived[0]
    assert d.text == "the user cannot commute by bicycle while the leg heals"
    assert d.depth == 1
    justs = await records.justifications_of(d.id)
    assert len(justs) == 1
    assert set(justs[0].premise_ids) == {a.id, b.id}
    assert justs[0].mode == "deduction"
    signals = await records.trust_signals(d.id)
    assert signals["provenance"] == Provenance.DERIVED
    assert signals["independent_grounds"] == 1
    await consolidate.close()
    await records.close()


# --- (b) cite-or-void / (c) verify rejection ------------------------------------


async def test_hallucinated_premises_and_failed_verify_store_nothing(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user cycles to work every morning")
    b = await records.add("the user cycles on weekends too")
    llm = StubLLM(
        _NOP,
        _dream("?", "a conclusion citing a ghost", ["not-a-real-id"]),  # voided pre-verify
    )
    consolidate = _consolidate(tmp_path, records, llm)
    report = await consolidate.run_once()
    assert report.derived == 0
    assert all(r.provenance == Provenance.GROUND for r in await records.list())

    # Now a properly-cited candidate the skeptic rejects.
    llm2 = StubLLM(
        _NOP,
        _dream("?", "the user is an olympic cyclist", [a.id, b.id]),
        _verify(supported=False),
    )
    consolidate2 = _consolidate(tmp_path, records, llm2)
    await records.confirm(a.id)  # move the watermark window
    report2 = await consolidate2.run_once()
    assert report2.derived == 0
    assert all(r.provenance == Provenance.GROUND for r in await records.list())
    await consolidate.close()
    await consolidate2.close()
    await records.close()


# --- (d) duplicate lands as corroborating justification -------------------------


async def test_duplicate_conclusion_corroborates_existing_record(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user declined the standup on monday")
    b = await records.add("the user declined the standup on friday")
    existing = await records.add("the user avoids the standup meetings")
    llm = StubLLM(
        _NOP,
        _dream("does the user avoid standups?", "the user avoids standup meetings",
               [a.id, b.id], mode="induction"),
        _verify(duplicate_of=existing.id),
    )
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.derived == 0
    assert report.corroborated == 1
    justs = await records.justifications_of(existing.id)
    assert len(justs) == 1
    assert set(justs[0].premise_ids) == {a.id, b.id}
    # Ground stays ground at depth 0 — corroboration is not pedigree.
    fresh = await records.get(existing.id)
    assert fresh.provenance == Provenance.GROUND
    assert fresh.depth == 0
    await consolidate.close()
    await records.close()


# --- (e) premise death -> unresolved -> recall-excluded -------------------------


async def test_premise_death_marks_dependent_unresolved_and_hides_it(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user cycles to work every morning")
    d = await records.add_derived(
        "the user gets daily exercise from the bicycle commute",
        premise_ids=[a.id], mode="deduction", question="does the user exercise?",
    )
    assert {r.id for r in await records.search("bicycle commute exercise", limit=5)} >= {d.id}

    replacement = await records.add("the user now drives to work")
    await records.supersede(a.id, replacement.id)

    fresh = await records.get(d.id)
    assert fresh.standing == Standing.UNRESOLVED
    # Excluded from recall while unresolved; still present for the UI.
    assert d.id not in {r.id for r in await records.search("bicycle commute exercise", limit=5)}
    assert d.id in {r.id for r in await records.list(limit=50)}
    await records.close()


# --- (f) JTMS: surviving justification keeps it active --------------------------


async def test_second_living_justification_survives_premise_death(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user cycles to work")
    b = await records.add("the user wears out a bike chain every quarter")
    d = await records.add_derived(
        "the user rides a bicycle regularly",
        premise_ids=[a.id], mode="deduction", question="does the user ride?",
    )
    await records.add_justification(
        d.id, premise_ids=[b.id], mode="induction", question="does the user ride?"
    )

    replacement = await records.add("the user moved and walks to work now")
    await records.supersede(a.id, replacement.id)

    fresh = await records.get(d.id)
    assert fresh.standing == Standing.ACTIVE  # b still supports it — never cascaded
    signals = await records.trust_signals(d.id)
    assert signals["justifications"] == 2
    assert signals["independent_grounds"] == 2  # disjoint evidence
    await records.close()


# --- (g) re-judgment: REAFFIRM / REVISE / RETIRE --------------------------------


async def test_rejudge_reaffirm_reactivates_on_live_premises(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user cycles to work daily on a road bike")
    d = await records.add_derived(
        "the user rides a bicycle daily",
        premise_ids=[a.id], mode="deduction", question="rides?",
    )
    successor = await records.add("the user cycles to work daily on a new gravel bike")
    await records.supersede(a.id, successor.id)
    assert (await records.get(d.id)).standing == Standing.UNRESOLVED

    llm = StubLLM(
        _NOP,  # lint judge for the successor's neighborhood
        _rejudge("REAFFIRM", premise_ids=[successor.id]),
    )
    consolidate = _consolidate(tmp_path, records, llm)
    report = await consolidate.run_once()

    assert report.reaffirmed == 1
    fresh = await records.get(d.id)
    assert fresh.standing == Standing.ACTIVE
    assert any(
        successor.id in j.premise_ids for j in await records.justifications_of(d.id)
    )
    await consolidate.close()
    await records.close()


async def test_rejudge_revise_supersedes_into_corrected_conclusion(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user works at acme as an engineer")
    d = await records.add_derived(
        "the user's employer is acme",
        premise_ids=[a.id], mode="deduction", question="employer?",
    )
    successor = await records.add("the user works at globex as an engineer")
    await records.supersede(a.id, successor.id)

    llm = StubLLM(
        _NOP,
        _rejudge("REVISE", text="the user's employer is globex", premise_ids=[successor.id]),
    )
    consolidate = _consolidate(tmp_path, records, llm)
    report = await consolidate.run_once()

    assert report.revised == 1
    old = await records.get(d.id)
    assert old.superseded_by is not None
    revised = await records.get(old.superseded_by)
    assert revised.text == "the user's employer is globex"
    assert revised.provenance == Provenance.DERIVED
    assert any(
        successor.id in j.premise_ids for j in await records.justifications_of(revised.id)
    )
    await consolidate.close()
    await records.close()


async def test_rejudge_retire_records_a_nogood_that_blocks_rederivation(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user mentioned the marathon project once")
    d = await records.add_derived(
        "the user is training for a marathon",
        premise_ids=[a.id], mode="abduction", question="training?",
    )
    replacement = await records.add("the marathon project is a software codename")
    await records.supersede(a.id, replacement.id)

    llm = StubLLM(
        _NOP,
        _rejudge("RETIRE", why="the premise was a codename, not athletics"),
    )
    consolidate = _consolidate(tmp_path, records, llm)
    report = await consolidate.run_once()

    assert report.retired == 1
    assert (await records.get(d.id)).standing == Standing.RETIRED
    nogoods = await records.nogoods_for([a.id])
    assert len(nogoods) == 1
    assert nogoods[0]["conclusion"] == "the user is training for a marathon"

    # The nogood reaches later dream prompts whose neighborhood overlaps.
    await records.confirm(replacement.id)
    llm2 = StubLLM(_NOP)
    consolidate2 = _consolidate(tmp_path, records, llm2)
    await consolidate2.run_once()
    dream_calls = [
        c for c in llm2.calls
        if c["response_format"] is not None and c["response_format"].__name__ == "DreamOps"
    ]
    assert not dream_calls or all(
        "marathon" not in c["messages"][1]["content"] or "NOGOODS" in c["messages"][1]["content"]
        for c in dream_calls
    )
    await consolidate.close()
    await consolidate2.close()
    await records.close()


# --- (h) depth cap / (i) cycle guard / (j) recursion -----------------------------


async def test_depth_cap_blocks_towering_speculation(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    base = await records.add("ground fact about cycling habits")
    d1 = await records.add_derived("level one cycling inference", premise_ids=[base.id], mode="deduction", question="q1")
    d2 = await records.add_derived("level two cycling inference", premise_ids=[d1.id], mode="deduction", question="q2")
    d3 = await records.add_derived("level three cycling inference", premise_ids=[d2.id], mode="deduction", question="q3")
    assert (d1.depth, d2.depth, d3.depth) == (1, 2, 3)

    llm = StubLLM(
        _NOP,
        _dream("q4", "level four cycling inference", [d3.id, d2.id]),
        # no verify queued: the depth cap must reject BEFORE verification
    )
    consolidate = _consolidate(tmp_path, records, llm)
    report = await consolidate.run_once()
    assert report.derived == 0
    verify_calls = [
        c for c in llm.calls
        if c["response_format"] is not None and c["response_format"].__name__ == "VerifyVerdict"
    ]
    assert verify_calls == []
    await consolidate.close()
    await records.close()


async def test_cyclic_justification_is_rejected(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("ground fact")
    d = await records.add_derived("inference from ground", premise_ids=[a.id], mode="deduction", question="q")
    with pytest.raises(ValueError):
        await records.add_justification(a.id, premise_ids=[d.id], mode="deduction", question="loop")
    await records.close()


async def test_recursion_derived_records_are_premises(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    g1 = await records.add("the user codes in python at work")
    g2 = await records.add("the user codes rust on weekends")
    d1 = await records.add_derived(
        "the user programs across multiple languages",
        premise_ids=[g1.id, g2.id], mode="induction", question="polyglot?",
    )
    d2 = await records.add_derived(
        "the user is a generalist software engineer",
        premise_ids=[d1.id], mode="abduction", question="generalist?",
    )
    assert d2.depth == 2
    base = await records.evidence_base(d2.id)
    assert base == {g1.id, g2.id}  # the stamp reaches through the chain to ground
    await records.close()
