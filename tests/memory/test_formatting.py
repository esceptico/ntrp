from datetime import datetime

from ntrp.memory.formatting import format_context
from ntrp.memory.models import Fact, FactContext, FactType, Observation


def make_fact(id: int, text: str) -> Fact:
    now = datetime.now()
    return Fact(
        id=id,
        text=text,
        fact_type=FactType.WORLD,
        embedding=None,
        source_type="test",
        source_ref=None,
        created_at=now,
        happened_at=None,
        last_accessed_at=now,
        access_count=0,
        consolidated_at=None,
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


class TestFormatContext:
    def test_empty_context(self):
        context = FactContext(facts=[], observations=[])
        assert format_context(context) == ""

    def test_facts_only(self):
        context = FactContext(
            facts=[make_fact(1, "Alice works at Google")],
            observations=[],
        )
        result = format_context(context)
        assert "## Memory" in result
        assert "### Facts" in result
        assert "Alice works at Google" in result
        assert "### Patterns" not in result

    def test_observations_only(self):
        context = FactContext(
            facts=[],
            observations=[make_observation(1, "Prefers Python for data analysis")],
        )
        result = format_context(context)
        assert "## Memory" in result
        assert "### Patterns" in result
        assert "Prefers Python" in result
        assert "### Facts" not in result

    def test_both_facts_and_observations(self):
        context = FactContext(
            facts=[make_fact(1, "Likes coffee")],
            observations=[make_observation(1, "Morning person")],
        )
        result = format_context(context)
        assert "### Patterns" in result
        assert "### Facts" in result
        assert "Likes coffee" in result
        assert "Morning person" in result
