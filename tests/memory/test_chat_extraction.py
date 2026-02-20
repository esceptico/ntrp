from unittest.mock import AsyncMock, patch

import pytest

from ntrp.memory.chat_extraction import (
    ChatExtractionSchema,
    _format_messages,
    extract_from_chat,
)


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
    {"role": "user", "content": "I decided to use Postgres for the new project"},
    {"role": "assistant", "content": "Good choice. I'll set up the schema."},
    {"role": "user", "content": "Also, John will handle the deployment"},
    {"role": "assistant", "content": "Got it."},
)


class TestFormatMessages:
    def test_basic_formatting(self):
        result = _format_messages(SAMPLE_MESSAGES)
        assert "user: I decided to use Postgres" in result
        assert "assistant: Good choice" in result

    def test_skips_tool_messages(self):
        messages = (
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "tool output here"},
            {"role": "assistant", "content": "response"},
        )
        result = _format_messages(messages)
        assert "tool output" not in result
        assert "user: hello" in result
        assert "assistant: response" in result

    def test_skips_session_handoff(self):
        messages = (
            {"role": "assistant", "content": "[Session State Handoff]\nSummary of prior context..."},
            {"role": "user", "content": "continuing now"},
        )
        result = _format_messages(messages)
        assert "Session State Handoff" not in result
        assert "user: continuing now" in result

    def test_skips_empty_content(self):
        messages = (
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "response"},
        )
        result = _format_messages(messages)
        assert result == "assistant: response"

    def test_skips_non_string_content(self):
        messages = (
            {"role": "user", "content": [{"type": "text", "text": "multimodal"}]},
            {"role": "assistant", "content": "response"},
        )
        result = _format_messages(messages)
        assert result == "assistant: response"

    def test_empty_messages(self):
        result = _format_messages(())
        assert result == ""


class TestExtractFromChat:
    @pytest.mark.asyncio
    async def test_returns_extracted_facts(self):
        schema = ChatExtractionSchema(facts=["User chose Postgres", "John handles deployment"])
        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(schema.model_dump_json())

        with patch("ntrp.memory.chat_extraction.get_completion_client", return_value=mock_client):
            facts = await extract_from_chat(SAMPLE_MESSAGES, "test-model")

        assert facts == ["User chose Postgres", "John handles deployment"]

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_facts(self):
        schema = ChatExtractionSchema(facts=[])
        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(schema.model_dump_json())

        with patch("ntrp.memory.chat_extraction.get_completion_client", return_value=mock_client):
            facts = await extract_from_chat(SAMPLE_MESSAGES, "test-model")

        assert facts == []

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
