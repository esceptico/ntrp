"""End-to-end: integration observations un-starve the cross-domain dream.

The whole point of the `observation` kind is that the dream (dreamer.py) has
orthogonal, multi-source material to connect. This proves it on a real
FilePageStore: observations land on per-source pages, the dream catalogs them
(store.list), retrieves them as evidence (store.search), and authors a cited
insight that bridges an observation page and a durable fact page (>=2 pages — the
dream's bar). Hermetic: a scripted fake LLM, no real model, no network.
"""

from pathlib import Path

import pytest

from ntrp.memory.dreamer import run_dream
from ntrp.memory.file_store import FilePageStore
from ntrp.memory.models import SourceRef

pytestmark = pytest.mark.asyncio


class DreamLLM:
    """Two scripted turns: a cross-topic question, then an insight citing an
    observation id + a fact id (which resolve to two different pages)."""

    def __init__(self, obs_id: str, fact_id: str):
        self._obs_id = obs_id
        self._fact_id = fact_id
        self.n = 0

    async def completion(self, *, messages, model, reasoning_effort=None, langfuse_name=None):
        self.n += 1
        if self.n == 1:
            content = "What connects the user's work and their email and calendar activity?"
        else:
            content = f"The user's email/calendar activity centers on their work focus. (because of ^{self._obs_id}, ^{self._fact_id})"
        msg = type("M", (), {"content": content})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


async def test_dream_connects_observations_to_facts(tmp_path: Path):
    store = FilePageStore(Path(tmp_path))  # no search index -> lexical search leg
    await store.open()

    # Durable facts (chat path) — land on me.md.
    fact = await store.add("The user works on Dex/Nexus.", kind="fact", source_ref=SourceRef("user", ""))
    for t in ("The user prefers async work.", "The user is based in Armenia.", "The user uses Obsidian."):
        await store.add(t, kind="fact", source_ref=SourceRef("user", ""))

    # Integration observations (gate-free) — land on observations/<source>.md.
    obs = await store.add("Email from Kevin about the Nexus work review.", kind="observation", source_ref=SourceRef("gmail", "g1"))
    await store.add("Email thread about an Ostium deployment.", kind="observation", source_ref=SourceRef("gmail", "g2"))
    await store.add("Calendar: 1:1 with Regina about work priorities.", kind="observation", source_ref=SourceRef("calendar", "c1"))

    # The observations live on their own per-source pages (not entity pages).
    assert (Path(tmp_path) / "observations" / "gmail.md").exists()
    assert (Path(tmp_path) / "observations" / "calendar.md").exists()

    # They ARE in the dream's catalog source (store.list, all kinds).
    listed = {r.id for r in await store.list(scopes=None, limit=None)}
    assert obs.id in listed and fact.id in listed

    out = await run_dream(store, DreamLLM(obs.id, fact.id), "memory-model")
    assert "insights written" in out and "skipped" not in out, out

    # An insight was authored (src:dreamer), connecting the observation + the fact.
    dreamed = [r for r in await store.list(scopes=None, limit=None) if r.source_ref and r.source_ref.kind == "dreamer"]
    assert len(dreamed) == 1, dreamed
    assert f"^{obs.id}" in dreamed[0].text or obs.id in dreamed[0].text


async def test_observation_flood_does_not_evict_facts_from_catalog(tmp_path: Path):
    """A high-volume integration day must not crowd durable facts out of the dream's
    question catalog — else the dream would bridge gmail↔calendar noise instead of
    life-domains, re-starving the very flow observations exist to feed."""
    from ntrp.memory.dreamer import OBS_CATALOG_CAP, _build_catalog

    store = FilePageStore(Path(tmp_path))
    await store.open()

    fact_ids = set()
    for i in range(5):
        r = await store.add(f"Durable fact number {i} about the user.", kind="fact", source_ref=SourceRef("user", ""))
        fact_ids.add(r.id)
    # Flood: many more observations than the cap, all dated today (newest-by-date).
    for i in range(OBS_CATALOG_CAP * 2):
        await store.add(f"Routine email number {i}.", kind="observation", source_ref=SourceRef("gmail", f"g{i}"))

    catalog = await _build_catalog(store)
    cat_ids = {r.id for r in catalog}

    assert fact_ids <= cat_ids, "durable facts must survive an observation flood"
    obs_in_catalog = [r for r in catalog if r.kind == "observation"]
    assert len(obs_in_catalog) == OBS_CATALOG_CAP, len(obs_in_catalog)  # observations are bounded, not unbounded
