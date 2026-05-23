import pytest

import ntrp.core.naming as naming
from tests.helpers import make_text_response


class FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    async def complete(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return make_text_response(self.content, model=model)


@pytest.mark.asyncio
async def test_generate_conversation_name_uses_session_prompt(monkeypatch):
    fake = FakeLLM('{"name": "Session naming prompts"}')
    monkeypatch.setattr(naming, "llm_client", fake)

    result = await naming.generate_conversation_name(
        "test-model",
        "please review research agent session naming prompts",
    )

    assert result == "Session naming prompts"
    assert fake.calls[0]["model"] == "test-model"
    assert fake.calls[0]["response_format"] is naming.NameOutput
    assert "research agent session naming prompts" in fake.calls[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_generate_agent_name_does_not_send_role_prefix(monkeypatch):
    fake = FakeLLM('{"name": "Summarize recent projects"}')
    monkeypatch.setattr(naming, "llm_client", fake)

    result = await naming.generate_agent_name(
        "test-model",
        "summarize recent projects",
    )

    assert result == "Summarize recent projects"
    assert fake.calls[0]["model"] == "test-model"
    assert fake.calls[0]["response_format"] is naming.NameOutput
    prompt_text = "\n".join(message["content"] for message in fake.calls[0]["messages"])
    assert "Research" not in prompt_text
    assert "summarize recent projects" in prompt_text


@pytest.mark.asyncio
async def test_generate_conversation_name_keeps_image_only_fallback(monkeypatch):
    fake = FakeLLM('{"name": "Should not be used"}')
    monkeypatch.setattr(naming, "llm_client", fake)

    result = await naming.generate_conversation_name("test-model", "", has_images=True)

    assert result == "Image Conversation"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_generate_agent_name_falls_back_when_model_fails(monkeypatch):
    class FailingLLM:
        async def complete(self, model, messages, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(naming, "llm_client", FailingLLM())

    result = await naming.generate_agent_name("test-model", "inspect eval harness")

    assert result == "Agent"


@pytest.mark.asyncio
async def test_generate_agent_name_rejects_research_prefix(monkeypatch):
    fake = FakeLLM('{"name": "Research eval test harness"}')
    monkeypatch.setattr(naming, "llm_client", fake)

    result = await naming.generate_agent_name("test-model", "inspect eval harness")

    assert result == "Agent"
