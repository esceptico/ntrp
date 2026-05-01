from datetime import datetime

from ntrp.memory.formatting import format_memory_context, format_memory_context_render, format_session_memory
from ntrp.memory.models import Fact, FactContext, FactKind, Observation, SourceType


def make_fact(id: int, text: str, kind: FactKind = FactKind.NOTE) -> Fact:
    now = datetime.now()
    return Fact(
        id=id,
        text=text,
        embedding=None,
        source_type=SourceType.EXPLICIT,
        source_ref=None,
        created_at=now,
        happened_at=None,
        last_accessed_at=now,
        access_count=0,
        consolidated_at=None,
        kind=kind,
    )


def make_observation(id: int, summary: str) -> Observation:
    now = datetime.now()
    return Observation(
        id=id,
        summary=summary,
        embedding=None,
        evidence_count=1,
        source_fact_ids=[],
        history=[],
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        access_count=0,
    )


class TestFormatMemoryContext:
    def test_empty_context(self):
        context = FactContext(facts=[], observations=[])
        assert format_memory_context(query_facts=context.facts, query_observations=context.observations) is None

    def test_facts_only(self):
        context = FactContext(
            facts=[make_fact(1, "Alice works at Google")],
            observations=[],
        )
        result = format_memory_context(query_facts=context.facts, query_observations=context.observations)
        assert "**Relevant**" in result
        assert "Alice works at Google" in result
        assert "**Patterns**" not in result

    def test_observations_only(self):
        context = FactContext(
            facts=[],
            observations=[make_observation(1, "Prefers Python for data analysis")],
        )
        result = format_memory_context(query_facts=context.facts, query_observations=context.observations)
        assert "**Patterns**" in result
        assert "Prefers Python" in result
        assert "**Relevant**" not in result

    def test_both_facts_and_observations(self):
        context = FactContext(
            facts=[make_fact(1, "Likes coffee")],
            observations=[make_observation(1, "Morning person")],
        )
        result = format_memory_context(query_facts=context.facts, query_observations=context.observations)
        assert "**Patterns**" in result
        assert "**Relevant**" in result
        assert "Likes coffee" in result
        assert "Morning person" in result

    def test_render_tracks_only_items_that_fit_budget(self):
        context = FactContext(
            facts=[
                make_fact(1, "short"),
                make_fact(2, "this fact is too long to fit in the remaining tiny budget"),
            ],
            observations=[],
        )

        render = format_memory_context_render(
            query_facts=context.facts,
            query_observations=context.observations,
            budget=64,
        )

        assert render is not None
        assert render.fact_ids == [1]
        assert "short" in render.text
        assert "too long" not in render.text

    def test_render_tracks_bundled_observation_sources(self):
        observation = make_observation(3, "User likes reliable memory")
        source = make_fact(4, "User asked for direct provenance")
        render = format_memory_context_render(
            query_facts=[],
            query_observations=[observation],
            bundled_sources={observation.id: [source]},
        )

        assert render is not None
        assert render.observation_ids == [3]
        assert render.fact_ids == [4]
        assert render.bundled_fact_ids == [4]

    def test_render_keeps_observation_when_sources_do_not_fit_budget(self):
        observation = make_observation(3, "User wants consolidated observations in prompt memory")
        source = make_fact(4, "User provided a very long source fact that should not evict the observation summary")
        render = format_memory_context_render(
            query_facts=[],
            query_observations=[observation],
            bundled_sources={observation.id: [source]},
            budget=96,
        )

        assert render is not None
        assert render.observation_ids == [3]
        assert render.fact_ids == []
        assert "consolidated observations" in render.text
        assert "very long source fact" not in render.text

    def test_render_clips_oversized_observation_instead_of_dropping_context(self):
        observation = make_observation(3, "User wants " + "consolidated observations " * 20)
        render = format_memory_context_render(
            query_facts=[],
            query_observations=[observation],
            budget=80,
        )

        assert render is not None
        assert render.observation_ids == [3]
        assert render.text.endswith("...")


class TestFormatSessionMemory:
    def test_profile_facts_are_sectioned(self):
        result = format_session_memory(
            profile_facts=[
                make_fact(1, "User is Timur", FactKind.IDENTITY),
                make_fact(2, "User prefers terse updates", FactKind.PREFERENCE),
            ],
            observations=[make_observation(4, "User is improving memory quality")],
            user_facts=[make_fact(3, "Legacy user fact")],
        )

        assert result.index("**Patterns**") < result.index("**Identity**")
        assert "**Identity**" in result
        assert "**Preferences**" in result
        assert "**About user**" in result
        assert "User is improving memory quality" in result
        assert "User is Timur" in result
        assert "User prefers terse updates" in result
