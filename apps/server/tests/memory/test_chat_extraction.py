from inspect import signature
from unittest.mock import AsyncMock, patch

import pytest

from ntrp.memory.chat_extraction import (
    CHAT_EXTRACTION_PROMPT,
    ChatExtractionSchema,
    ExtractedChatFact,
    _format_messages,
    extract_from_chat,
)
from ntrp.memory.models import FactKind, FactLifetime


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


SAMPLE_MESSAGES = (
    {"role": "user", "content": "I decided to use Postgres for the new project", "message_id": "m-1"},
    {"role": "assistant", "content": "Good choice. I'll set up the schema.", "message_id": "m-2"},
    {"role": "user", "content": "Also, John will handle the deployment", "message_id": "m-3"},
    {"role": "assistant", "content": "Got it.", "message_id": "m-4"},
)


class TestFormatMessages:
    def test_basic_formatting(self):
        result = _format_messages(SAMPLE_MESSAGES)
        assert "USER [m-1] (evidence): I decided to use Postgres" in result
        assert "ASSISTANT [m-2] (context only): Good choice" in result

    def test_skips_tool_messages(self):
        messages = (
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "tool output here"},
            {"role": "assistant", "content": "response"},
        )
        result = _format_messages(messages)
        assert "tool output" not in result
        assert "USER [message-0] (evidence): hello" in result
        assert "ASSISTANT [message-2] (context only): response" in result

    def test_skips_session_handoff(self):
        messages = (
            {"role": "assistant", "content": "[Session State Handoff]\nSummary of prior context..."},
            {"role": "user", "content": "continuing now"},
        )
        result = _format_messages(messages)
        assert "Session State Handoff" not in result
        assert "USER [message-1] (evidence): continuing now" in result

    def test_skips_empty_content(self):
        messages = (
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "response"},
        )
        result = _format_messages(messages)
        assert result == "ASSISTANT [message-1] (context only): response"

    def test_skips_non_string_content(self):
        messages = (
            {"role": "user", "content": [{"type": "text", "text": "multimodal"}]},
            {"role": "assistant", "content": "response"},
        )
        result = _format_messages(messages)
        assert result == "ASSISTANT [message-1] (context only): response"

    def test_empty_messages(self):
        result = _format_messages(())
        assert result == ""


class TestExtractFromChat:
    def test_prompt_describes_source_of_truth_not_patterns(self):
        prompt = CHAT_EXTRACTION_PROMPT.render(conversation="user: I prefer raw SQL")

        assert "source-of-truth memory facts" in prompt
        assert "Do not write observations, patterns" in prompt
        assert "Patterns not directly stated" in prompt
        assert "Assign exactly one kind" in prompt
        assert "Assign exactly one lifetime" in prompt

    def test_extraction_prompt_has_no_policy_note_slot(self):
        prompt = CHAT_EXTRACTION_PROMPT.render(
            conversation="user: I prefer raw SQL",
            policy_context="- memory.extraction.feedback: Add more rules",
        )

        assert "APPROVED MEMORY POLICY NOTES" not in prompt
        assert "memory.extraction.feedback" not in prompt

    def test_extract_from_chat_accepts_only_messages_and_model(self):
        assert "policy_context" not in signature(extract_from_chat).parameters

    @pytest.mark.asyncio
    async def test_returns_extracted_facts(self):
        schema = ChatExtractionSchema(
            facts=[
                ExtractedChatFact(
                    text="User chose Postgres",
                    kind=FactKind.DECISION,
                    salience=1,
                    entities=["User", "Postgres"],
                    evidence_message_ids=["m-1"],
                ),
                ExtractedChatFact(
                    text="John handles deployment",
                    kind=FactKind.RELATIONSHIP,
                    entities=["John"],
                    evidence_message_ids=["m-3"],
                ),
            ]
        )
        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(schema.model_dump_json())

        with patch("ntrp.memory.chat_extraction.get_completion_client", return_value=mock_client):
            facts = await extract_from_chat(SAMPLE_MESSAGES, "test-model")

        assert [fact.text for fact in facts] == ["User chose Postgres", "John handles deployment"]
        assert facts[0].kind == FactKind.DECISION
        assert facts[0].salience == 1
        assert facts[0].entities == ["User", "Postgres"]
        assert facts[0].evidence_message_ids == ["m-1"]

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_facts(self):
        schema = ChatExtractionSchema(facts=[])
        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(schema.model_dump_json())

        with patch("ntrp.memory.chat_extraction.get_completion_client", return_value=mock_client):
            facts = await extract_from_chat(SAMPLE_MESSAGES, "test-model")

        assert facts == []

    @pytest.mark.asyncio
    async def test_drops_temporary_facts_without_expiry(self):
        schema = ChatExtractionSchema(
            facts=[
                ExtractedChatFact(text="User is debugging login today", lifetime=FactLifetime.TEMPORARY),
                ExtractedChatFact(text="User prefers direct answers", kind=FactKind.PREFERENCE),
            ]
        )
        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(schema.model_dump_json())

        with patch("ntrp.memory.chat_extraction.get_completion_client", return_value=mock_client):
            facts = await extract_from_chat(SAMPLE_MESSAGES, "test-model")

        assert [fact.text for fact in facts] == ["User prefers direct answers"]

    @pytest.mark.asyncio
    async def test_returns_empty_for_tool_only_messages(self):
        messages = (
            {"role": "tool", "content": "output"},
            {"role": "tool", "content": "more output"},
        )
        facts = await extract_from_chat(messages, "test-model")
        assert facts == []

    @pytest.mark.asyncio
    async def test_handles_llm_error(self):
        mock_client = AsyncMock()
        mock_client.completion.side_effect = RuntimeError("LLM down")

        with patch("ntrp.memory.chat_extraction.get_completion_client", return_value=mock_client):
            facts = await extract_from_chat(SAMPLE_MESSAGES, "test-model")

        assert facts == []
