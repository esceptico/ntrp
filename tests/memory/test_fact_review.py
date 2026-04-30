from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from ntrp.memory.fact_review import (
    FACT_KIND_REVIEW_PROMPT,
    FactMetadataSuggestion,
    FactMetadataSuggestionSchema,
    suggest_fact_metadata,
)
from ntrp.memory.models import Fact, FactKind, SourceType


def mock_llm_response(content: str):
    return type(
        "Response",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {"message": type("Message", (), {"content": content})()},
                )()
            ]
        },
    )()


def _fact(fact_id: int, text: str) -> Fact:
    now = datetime.now(UTC)
    return Fact(
        id=fact_id,
        text=text,
        embedding=None,
        source_type=SourceType.CHAT,
        source_ref="test",
        created_at=now,
        happened_at=None,
        last_accessed_at=now,
        access_count=0,
    )


def test_fact_kind_review_prompt_is_review_only():
    prompt = FACT_KIND_REVIEW_PROMPT.render(facts_json="[]")

    assert "metadata suggestions only" in prompt
    assert "Prefer \"note\" when uncertain" in prompt
    assert "Do not suggest supersession" in prompt


@pytest.mark.asyncio
async def test_suggest_fact_metadata_filters_and_normalizes_results():
    facts = [_fact(1, "User prefers raw SQL"), _fact(2, "User is debugging login today")]
    schema = FactMetadataSuggestionSchema(
        suggestions=[
            FactMetadataSuggestion(
                fact_id=1,
                kind=FactKind.PREFERENCE,
                salience=1,
                confidence=0.9,
                reason="stable user preference",
            ),
            FactMetadataSuggestion(
                fact_id=2,
                kind=FactKind.TEMPORARY,
                salience=2,
                confidence=0.8,
                reason="short-lived debugging state",
            ),
            FactMetadataSuggestion(
                fact_id=999,
                kind=FactKind.IDENTITY,
                reason="not in input",
            ),
            FactMetadataSuggestion(
                fact_id=1,
                kind=FactKind.NOTE,
                reason="duplicate",
            ),
        ]
    )
    mock_client = AsyncMock()
    mock_client.completion.return_value = mock_llm_response(schema.model_dump_json())

    with patch("ntrp.memory.fact_review.get_completion_client", return_value=mock_client):
        suggestions = await suggest_fact_metadata(facts, "test-model")

    assert [suggestion.fact_id for suggestion in suggestions] == [1, 2]
    assert suggestions[0].kind == FactKind.PREFERENCE
    assert suggestions[0].salience == 1
    assert suggestions[1].kind == FactKind.NOTE
    assert suggestions[1].salience == 1
    assert "no expiry" in suggestions[1].reason
