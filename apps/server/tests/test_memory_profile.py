"""resident_profile — the always-resident memory block (ntrp/memory/profile.py).

Projects directives + durable user facts + pins from the flat pool into the
system-prompt block that rides every turn. Hermetic: a tmp memory.db, FTS-only.
"""

from pathlib import Path

import pytest

from ntrp.memory.profile import DIRECTIVE_CHAR_BUDGET, FACT_CHAR_BUDGET, resident_profile
from ntrp.memory.records import RecordStore

pytestmark = pytest.mark.asyncio


def _store(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path / "memory.db", search_index=None)


async def test_profile_carries_directives_and_facts_not_sources(tmp_path: Path):
    store = _store(tmp_path)
    await store.add("respond tersely", kind="directive", scope_kind="global")
    await store.add("the user lives in Munich", kind="fact", scope_kind="user")
    await store.add("https://example.com", kind="source", scope_kind="user")

    block = await resident_profile(store)

    assert block.startswith("## Profile")
    assert "respond tersely" in block
    assert "the user lives in Munich" in block
    assert "example.com" not in block  # sources are not standing memory
    # directives sort ahead of facts so behaviour rules survive truncation
    assert block.index("respond tersely") < block.index("Munich")
    await store.close()


async def test_profile_is_none_without_a_store():
    assert await resident_profile(None) is None


async def test_profile_respects_char_budget(tmp_path: Path):
    store = _store(tmp_path)
    await store.add("ALWAYS keep this rule", kind="directive", scope_kind="global")
    for i in range(400):
        await store.add(f"fact number {i} " + "x" * 40, kind="fact", scope_kind="user")

    block = await resident_profile(store)

    assert len(block) <= DIRECTIVE_CHAR_BUDGET + FACT_CHAR_BUDGET + len("## Profile\n\n") + 160
    assert "ALWAYS keep this rule" in block  # the directive is never truncated away
    await store.close()


async def test_verbose_directives_do_not_starve_facts(tmp_path: Path):
    store = _store(tmp_path)
    for i in range(20):
        await store.add("rule " + "y" * 300 + f" {i}", kind="directive", scope_kind="global")
    await store.add("the user is named Tim", kind="fact", scope_kind="user")

    block = await resident_profile(store)

    assert "the user is named Tim" in block  # facts get their own guaranteed slice
    await store.close()
