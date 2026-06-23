"""LLM-synthesized memory pages (artifacts.py: me.md / dossiers / active-work.md).

Hermetic: a fake completion client stands in for the curator's LLM. Exercises the
synthesis overlay, provenance verification (a fabricated `(record:...)` cite
falls back to the mechanical brief), the insufficient-records sentinel, and the
invariant that a cheap mechanical sync never clobbers a synthesized page.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from ntrp.memory import prompts_synthesis
from ntrp.memory.artifacts import SYNTHESIS_SOURCE, ArtifactMemoryStore
from ntrp.memory.models import Kind
from ntrp.memory.records import RecordStore

pytestmark = pytest.mark.asyncio

_ID_RE = re.compile(r"\[([0-9a-f]{8})\]")


def _first_id(user_msg: str) -> str:
    m = _ID_RE.search(user_msg)
    return m.group(1) if m else "00000000"


class FakeLLM:
    """Routes by the system prompt's identity line; cites a real provided id so
    provenance validation passes unless a test overrides the responder."""

    def __init__(self, responder=None):
        self.responder = responder or self._default
        self.calls = 0

    def _default(self, system: str, user: str) -> str:
        first = _first_id(user)
        if system.startswith("You write `me.md`"):
            return f"# Profile\n\n## Identity\nYou test ntrp memory (record:{first})."
        if system.startswith("You write a single topic page"):
            title = user.split("\n", 1)[0].removeprefix("Subject: ").strip()
            return f"# {title}\n\n## What we know\n{title} is a synthesized subject (record:{first})."
        if system.startswith("You write `active-work.md`"):
            return f"# Active work\n\nShipping the synthesis rework (record:{first})."
        return f"(record:{first})"

    async def completion(self, *, messages, model, langfuse_name=None, **kw):
        self.calls += 1
        system = messages[0]["content"]
        user = messages[1]["content"]
        content = self.responder(system, user)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


async def _store(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path / "memory.db", search_index=None)


async def _two_subject_records(records: RecordStore) -> None:
    r1 = await records.add("Regina co-founded ThirdLayer and leads product", kind=Kind.FACT)
    r2 = await records.add("Regina has a standing weekly 1:1 with the user", kind=Kind.FACT)
    await records.set_labels(r1.id, [], entity_labels=["Regina"])
    await records.set_labels(r2.id, [], entity_labels=["Regina"])


async def test_synthesis_writes_profile_and_dossier(tmp_path: Path):
    records = await _store(tmp_path)
    await records.add("answer concisely; no walls of text", kind=Kind.DIRECTIVE)
    await records.add("the user is a research engineer at ThirdLayer", kind=Kind.FACT, scope_kind="user")
    await _two_subject_records(records)
    store = ArtifactMemoryStore(tmp_path / "artifacts")

    await store.export_from_records(records, llm=FakeLLM(), model="fake")

    me = store.read_artifact("me.md")
    assert me.source == SYNTHESIS_SOURCE
    assert me.title == "Profile"
    assert "## Identity" in me.content
    assert "(record:" in me.content

    dossier = store.read_artifact("entities/regina.md")
    assert dossier.source == SYNTHESIS_SOURCE  # LLM-written, not the bullet brief
    assert "synthesized subject" in dossier.content
    assert "_Compiled subject brief" not in dossier.content  # not the mechanical body
    await records.close()


async def test_profile_links_only_generated_dossier_titles(tmp_path: Path):
    records = await _store(tmp_path)
    await records.add("the user relies on Codex for coding work", kind=Kind.FACT, scope_kind="user")
    codex = await records.add("Codex is a coding tool the user uses heavily", kind=Kind.FACT)
    await records.set_labels(codex.id, [], entity_labels=["Codex"])
    await _two_subject_records(records)
    store = ArtifactMemoryStore(tmp_path / "artifacts")

    def linker(system: str, user: str) -> str:
        first = _first_id(user)
        if system.startswith("You write `me.md`"):
            assert "- Regina" in user
            assert "- Codex" not in user
            return (
                "# Profile\n\n"
                "## Key relationships / tools\n"
                f"[[Regina]] is a generated dossier (record:{first}).\n"
                f"[[Codex]] is only mentioned once (record:{first})."
            )
        return FakeLLM()._default(system, user)

    await store.export_from_records(records, llm=FakeLLM(linker), model="fake")

    me = store.read_artifact("me.md")
    assert "[[Regina]]" in me.content
    assert "[[Codex]]" not in me.content
    assert "Codex is only mentioned once" in me.content
    await records.close()


async def test_fabricated_citation_falls_back_to_mechanical(tmp_path: Path):
    records = await _store(tmp_path)
    await _two_subject_records(records)
    store = ArtifactMemoryStore(tmp_path / "artifacts")

    # Cite an id we never handed the model -> provenance check fails -> mechanical.
    def liar(system: str, user: str) -> str:
        if system.startswith("You write a single topic page"):
            return "# Regina\n\n## What we know\nFabricated (record:deadbeef)."
        return FakeLLM()._default(system, user)

    await store.export_from_records(records, llm=FakeLLM(liar), model="fake")

    dossier = store.read_artifact("entities/regina.md")
    assert dossier.source == "consolidate"  # mechanical fallback
    assert "_Compiled subject brief" in dossier.content
    assert "deadbeef" not in dossier.content
    await records.close()


async def test_insufficient_sentinel_falls_back_to_mechanical(tmp_path: Path):
    records = await _store(tmp_path)
    await _two_subject_records(records)
    store = ArtifactMemoryStore(tmp_path / "artifacts")

    def gate_fail(system: str, user: str) -> str:
        if system.startswith("You write a single topic page"):
            return prompts_synthesis.INSUFFICIENT_DOSSIER
        return FakeLLM()._default(system, user)

    await store.export_from_records(records, llm=FakeLLM(gate_fail), model="fake")

    dossier = store.read_artifact("entities/regina.md")
    assert dossier.source == "consolidate"
    assert "_Compiled subject brief" in dossier.content
    await records.close()


async def test_mechanical_sync_preserves_synthesized_pages(tmp_path: Path):
    records = await _store(tmp_path)
    await _two_subject_records(records)
    store = ArtifactMemoryStore(tmp_path / "artifacts")

    await store.export_from_records(records, llm=FakeLLM(), model="fake")
    synthesized = store.read_artifact("entities/regina.md").content
    me_before = store.read_artifact("me.md").content
    assert "synthesized subject" in synthesized

    # A cheap mechanical sync (no LLM) must NOT downgrade the synthesized pages.
    await store.export_from_records(records)

    after = store.read_artifact("entities/regina.md")
    assert after.source == SYNTHESIS_SOURCE
    assert after.content == synthesized  # untouched
    assert store.read_artifact("me.md").content == me_before  # me.md survives too
    await records.close()


async def test_mechanical_only_never_writes_profile(tmp_path: Path):
    records = await _store(tmp_path)
    await _two_subject_records(records)
    store = ArtifactMemoryStore(tmp_path / "artifacts")

    await store.export_from_records(records)  # mechanical, no LLM

    with pytest.raises(FileNotFoundError):
        store.read_artifact("me.md")
    with pytest.raises(FileNotFoundError):
        store.read_artifact("active-work.md")
    # mechanical still produces the bullet brief
    assert store.read_artifact("entities/regina.md").source == "consolidate"
    await records.close()


async def test_slug_collision_flip_does_not_strand_a_subject(tmp_path: Path):
    """Two labels that slugify to the same file ('O-1A' and 'O 1A' -> o-1a.md):
    after a synthesized rebuild, a rank-flip + mechanical sync must not let the
    old owner's synthesized page squat the slug while the new top subject gets no
    page. Every ranked subject must end up with a page, correctly titled."""
    records = await _store(tmp_path)
    a1 = await records.add("O-1A petition requires extraordinary-ability evidence", kind=Kind.FACT)
    a2 = await records.add("O-1A premium processing takes 15 days", kind=Kind.FACT)
    a3 = await records.add("O-1A needs an advisory opinion letter", kind=Kind.FACT)
    b1 = await records.add("O 1A travel is constrained by cost", kind=Kind.FACT)
    b2 = await records.add("O 1A dependents get O-3 status", kind=Kind.FACT)
    for r in (a1, a2, a3):
        await records.set_labels(r.id, [], entity_labels=["O-1A"])
    for r in (b1, b2):
        await records.set_labels(r.id, [], entity_labels=["O 1A"])
    store = ArtifactMemoryStore(tmp_path / "artifacts")
    await store.export_from_records(records, llm=FakeLLM(), model="fake")  # A(3) owns o-1a.md

    # Flip the lead: give "O 1A" more records, then a cheap mechanical sync.
    b3 = await records.add("O 1A spouse may study but not work", kind=Kind.FACT)
    b4 = await records.add("O 1A interview was scheduled in Yerevan", kind=Kind.FACT)
    for r in (b3, b4):
        await records.set_labels(r.id, [], entity_labels=["O 1A"])
    await store.export_from_records(records)  # mechanical

    pages = {a.path: a for a in store.list_artifacts() if a.path.startswith("entities/")}
    titles = {p.title for p in pages.values() if p.path not in ("entities/index.md", "entities/needs-triage.md")}
    assert "O-1A" in titles and "O 1A" in titles  # both subjects have a page, neither stranded
    # The bare slug must hold the current top subject (B, 4 records), not A's squatting prose.
    assert store.read_artifact("entities/o-1a.md").title == "O 1A"
    await records.close()


async def test_quoted_record_token_does_not_reject_valid_page(tmp_path: Path):
    """A record whose text literally contains a `record:HEX` token (e.g. a commit
    ref) must not make a correctly-cited synthesized page fail provenance and fall
    back to the bullet brief."""
    records = await _store(tmp_path)
    r1 = await records.add("Regina reverted commit record:65c334bf during the rebuild", kind=Kind.FACT)
    r2 = await records.add("Regina leads product at ThirdLayer", kind=Kind.FACT)
    await records.set_labels(r1.id, [], entity_labels=["Regina"])
    await records.set_labels(r2.id, [], entity_labels=["Regina"])
    store = ArtifactMemoryStore(tmp_path / "artifacts")

    # The model correctly cites a real id AND quotes the record's `record:65c334bf`
    # phrasing. The quoted token must be ignored by the provenance check.
    def quoter(system: str, user: str) -> str:
        first = _first_id(user)
        if system.startswith("You write a single topic page"):
            return f"# Regina\n\nReverted commit record:65c334bf during the rebuild (record:{first})."
        return FakeLLM()._default(system, user)

    await store.export_from_records(records, llm=FakeLLM(quoter), model="fake")

    dossier = store.read_artifact("entities/regina.md")
    assert dossier.source == SYNTHESIS_SOURCE  # NOT rejected to mechanical
    assert "record:65c334bf" in dossier.content  # quoted token preserved verbatim
    await records.close()


async def test_dropped_synthesized_subject_is_pruned(tmp_path: Path):
    records = await _store(tmp_path)
    await _two_subject_records(records)
    store = ArtifactMemoryStore(tmp_path / "artifacts")
    await store.export_from_records(records, llm=FakeLLM(), model="fake")
    assert store.read_artifact("entities/regina.md").source == SYNTHESIS_SOURCE

    # Forget both Regina records -> subject drops below threshold -> page pruned
    # even though it was synthesized (preserved-but-orphaned must not linger).
    for hit in await records.search("Regina"):
        await records.delete(hit.id)
    await store.export_from_records(records, llm=FakeLLM(), model="fake")

    with pytest.raises(FileNotFoundError):
        store.read_artifact("entities/regina.md")
    await records.close()
