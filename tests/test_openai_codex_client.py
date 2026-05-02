import pytest
from pydantic import BaseModel

from ntrp.agent import Choice, CompletionResponse, FinishReason, Message, Role, Usage
from ntrp.llm.openai_codex import OpenAICodexClient


class _Structured(BaseModel):
    ok: bool


class _FakeItem:
    def __init__(self, data: dict):
        self._data = data

    def model_dump(self, exclude_none: bool = True) -> dict:
        return self._data


class _InputDetails:
    cached_tokens = 7


class _Usage:
    input_tokens = 20
    output_tokens = 5
    input_tokens_details = _InputDetails()


class _Response:
    status = "completed"
    usage = _Usage()

    output = [
        _FakeItem(
            {
                "type": "reasoning",
                "encrypted_content": "encrypted",
                "content": [{"type": "reasoning_text", "text": "thinking"}],
            }
        ),
        _FakeItem(
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "hello"}],
            }
        ),
        _FakeItem(
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "Read",
                "arguments": '{"path":"README.md"}',
            }
        ),
    ]


class _EmptyResponse:
    status = "completed"
    usage = _Usage()
    output = []


def test_prepare_responses_request_uses_codex_model_and_response_shapes():
    client = OpenAICodexClient()

    request = client._prepare(
        messages=[
            {"role": Role.SYSTEM, "content": "system"},
            {"role": Role.USER, "content": [{"type": "text", "text": "hi"}]},
            {
                "role": Role.ASSISTANT,
                "content": "",
                "reasoning_encrypted_content": "encrypted-prev",
                "tool_calls": [{"id": "call_1", "function": {"name": "Read", "arguments": "{}"}}],
            },
            {"role": Role.TOOL, "tool_call_id": "call_1", "content": "done"},
        ],
        model="openai-codex/gpt-5.4",
        tools=[{"type": "function", "function": {"name": "Read", "parameters": {"type": "object"}}}],
        tool_choice={"type": "function", "function": {"name": "Read"}},
        temperature=0.3,
        max_tokens=100,
        reasoning_effort="high",
        response_format=_Structured,
        prompt_cache_key="session-1",
    )

    assert request["model"] == "gpt-5.4"
    assert request["store"] is False
    assert "temperature" not in request
    assert "max_output_tokens" not in request
    assert request["instructions"] == "system"
    assert request["input"][0]["content"] == [{"type": "input_text", "text": "hi"}]
    assert request["input"][1] == {"type": "reasoning", "encrypted_content": "encrypted-prev", "summary": []}
    assert request["input"][2] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "Read",
        "arguments": "{}",
        "status": "completed",
    }
    assert request["input"][3] == {"type": "function_call_output", "call_id": "call_1", "output": "done"}
    assert request["tools"] == [
        {
            "type": "function",
            "name": "Read",
            "description": "",
            "parameters": {"type": "object"},
            "strict": False,
        }
    ]
    assert request["tool_choice"] == {"type": "function", "name": "Read"}
    assert request["reasoning"] == {"effort": "high", "summary": "auto"}
    assert request["text"]["format"]["name"] == "_Structured"
    assert request["prompt_cache_key"] == "session-1"


def test_parse_response_collects_text_reasoning_tools_and_usage():
    parsed = OpenAICodexClient()._parse_response(_Response(), "openai-codex/gpt-5.4")

    choice = parsed.choices[0]
    assert choice.finish_reason == FinishReason.TOOL_CALLS
    assert choice.message.content == "hello"
    assert choice.message.reasoning_content == "thinking"
    assert choice.message.reasoning_encrypted_content == "encrypted"
    assert choice.message.tool_calls is not None
    assert choice.message.tool_calls[0].id == "call_1"
    assert choice.message.tool_calls[0].function.name == "Read"
    assert parsed.usage.prompt_tokens == 13
    assert parsed.usage.cache_read_tokens == 7
    assert parsed.usage.completion_tokens == 5


def test_parse_response_accepts_stream_completed_items():
    parsed = OpenAICodexClient()._parse_response(
        _EmptyResponse(),
        "openai-codex/gpt-5.4-mini",
        [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "ok"}],
            },
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "used state"}],
                "encrypted_content": "encrypted-stream",
            },
            {
                "type": "function_call",
                "call_id": "call_2",
                "name": "Read",
                "arguments": '{"path":"README.md"}',
            },
        ],
    )

    choice = parsed.choices[0]
    assert choice.message.content == "ok"
    assert choice.message.reasoning_content == "used state"
    assert choice.message.reasoning_encrypted_content == "encrypted-stream"
    assert choice.message.tool_calls is not None
    assert choice.message.tool_calls[0].id == "call_2"
    assert choice.finish_reason == FinishReason.TOOL_CALLS


@pytest.mark.asyncio
async def test_completion_consumes_streaming_response(monkeypatch):
    async def fake_stream(self, **kwargs):
        yield "ignored"
        yield CompletionResponse(
            choices=[
                Choice(
                    message=Message(
                        role=Role.ASSISTANT,
                        content="ok",
                        tool_calls=None,
                        reasoning_content=None,
                    ),
                    finish_reason=FinishReason.STOP,
                )
            ],
            usage=Usage(),
            model=kwargs["model"],
        )

    monkeypatch.setattr(OpenAICodexClient, "_stream_completion", fake_stream)

    parsed = await OpenAICodexClient()._completion(
        messages=[{"role": Role.USER, "content": "hi"}],
        model="openai-codex/gpt-5.5",
    )

    assert parsed.model == "openai-codex/gpt-5.5"
    assert parsed.choices[0].message.content == "ok"
