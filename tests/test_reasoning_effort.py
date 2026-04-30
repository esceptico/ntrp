import pytest
from fastapi import HTTPException

from ntrp.config import Config
from ntrp.llm.anthropic import AnthropicClient
from ntrp.llm.models import get_model
from ntrp.server.routers.settings import _validate_reasoning_patch


def test_reasoning_effort_patch_rejects_unsupported_model_value():
    fields = {"reasoning_effort": "max"}
    config = Config(memory=False, chat_model="gpt-5.2")

    with pytest.raises(HTTPException):
        _validate_reasoning_patch(fields, config)


def test_reasoning_effort_patch_clears_stale_effort_when_chat_model_changes():
    fields = {"chat_model": "qwen/qwen3.5-27b"}
    config = Config(memory=False, chat_model="gpt-5.2", reasoning_effort="high")

    _validate_reasoning_patch(fields, config)

    assert fields["reasoning_effort"] is None


def test_opus_4_7_exposes_adaptive_efforts():
    model = get_model("claude-opus-4-7")

    assert model.max_context_tokens == 1_000_000
    assert model.reasoning_efforts == ("low", "medium", "high", "xhigh", "max")


def test_opus_4_7_reasoning_uses_adaptive_thinking_and_output_effort():
    client = AnthropicClient(api_key="test")

    request = client._build_request(
        model="claude-opus-4-7",
        messages=[{"role": "user", "content": "hi"}],
        system=None,
        tools=None,
        tool_choice=None,
        temperature=0,
        max_tokens=128_000,
        reasoning_effort="xhigh",
    )

    assert request["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert request["output_config"] == {"effort": "xhigh"}
    assert "temperature" not in request
