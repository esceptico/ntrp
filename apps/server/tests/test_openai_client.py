from types import SimpleNamespace

import httpx
import pytest

from ntrp.agent.types.llm import ToolCallStreamDelta
from ntrp.llm.openai import OpenAIClient
from ntrp.llm.openai_responses import (
    buffered_stream_responses_completion,
    complete_responses_completion,
    stream_responses_completion,
)


def test_native_openai_request_includes_prompt_cache_key():
    client = OpenAIClient(api_key="test")

    request = client._prepare(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-5.2",
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
        reasoning_effort=None,
        response_format=None,
        prompt_cache_key="session-1",
    )

    assert request["prompt_cache_key"] == "session-1"


def test_openai_compatible_request_omits_prompt_cache_key():
    client = OpenAIClient(api_key="test", base_url="https://example.test", native_openai=False)

    request = client._prepare(
        messages=[{"role": "user", "content": "hi"}],
        model="custom-model",
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
        reasoning_effort=None,
        response_format=None,
        prompt_cache_key="session-1",
    )

    assert "prompt_cache_key" not in request


def test_chat_completions_request_formats_image_blocks_as_data_urls():
    client = OpenAIClient(api_key="test")

    request = client._prepare(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "inspect"},
                    {"type": "image", "media_type": "image/png", "data": "iVBORw0KGgo="},
                ],
            }
        ],
        model="gpt-5.2",
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
        reasoning_effort=None,
        response_format=None,
    )

    assert request["messages"][0]["content"] == [
        {"type": "text", "text": "inspect"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
    ]


def test_chat_completions_request_strips_internal_tool_result_data():
    client = OpenAIClient(api_key="test")

    request = client._prepare(
        messages=[
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "Started background agent.",
                "data": {"child_agent": {"child_run_id": "child-run-1"}},
            }
        ],
        model="gpt-5.2",
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
        reasoning_effort=None,
        response_format=None,
    )

    assert request["messages"] == [
        {"role": "tool", "tool_call_id": "call_1", "content": "Started background agent."}
    ]


def test_responses_request_formats_image_blocks_as_input_images():
    client = OpenAIClient(api_key="test")

    request = client._prepare_responses(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "inspect"},
                    {"type": "image", "media_type": "image/jpeg", "data": "/9j/4A=="},
                ],
            }
        ],
        model="gpt-5.5",
        tools=[{"type": "function", "function": {"name": "Search", "parameters": {"type": "object"}}}],
        tool_choice="auto",
        temperature=None,
        max_tokens=None,
        reasoning_effort="high",
        response_format=None,
    )

    assert request["input"][0]["content"] == [
        {"type": "input_text", "text": "inspect"},
        {"type": "input_image", "detail": "auto", "image_url": "data:image/jpeg;base64,/9j/4A=="},
    ]


class _FakeItem:
    def __init__(self, data: dict):
        self._data = data

    def model_dump(self, exclude_none: bool = True) -> dict:
        return self._data


class _InputDetails:
    cached_tokens = 0


class _Usage:
    input_tokens = 12
    output_tokens = 3
    input_tokens_details = _InputDetails()


class _Response:
    status = "completed"
    usage = _Usage()

    output = [
        _FakeItem(
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "ok"}],
            }
        )
    ]


class _Event:
    def __init__(self, data: dict, response=None):
        self._data = data
        self.response = response

    def model_dump(self, exclude_none: bool = True) -> dict:
        return self._data


class _Stream:
    def __init__(self, events: list[_Event | BaseException]):
        self._events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            event = next(self._events)
        except StopIteration:
            raise StopAsyncIteration
        if isinstance(event, BaseException):
            raise event
        return event


class _FakeResponses:
    def __init__(self):
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs.get("stream"):
            return _Stream(
                [
                    _Event({"type": "response.output_text.delta", "delta": "ok"}),
                    _Event({"type": "response.completed"}, response=_Response()),
                ]
            )
        return _Response()


class _FlakyAfterDeltaResponses:
    def __init__(self):
        self.calls = 0
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        self.calls += 1
        if self.calls == 1:
            return _Stream(
                [
                    _Event({"type": "response.output_text.delta", "delta": "partial"}),
                    httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
                ]
            )
        return _Stream(
            [
                _Event({"type": "response.output_text.delta", "delta": "ok"}),
                _Event({"type": "response.completed"}, response=_Response()),
            ]
        )


class _FlakyAfterDeltaOpenAI:
    def __init__(self):
        self.responses = _FlakyAfterDeltaResponses()


class _FakeChatCompletions:
    async def create(self, **kwargs):
        raise AssertionError("chat completions should not be used")


class _FakeOpenAI:
    def __init__(self):
        self.responses = _FakeResponses()
        self.chat = type("Chat", (), {"completions": _FakeChatCompletions()})()


class _DisconnectingResponses:
    async def create(self, **kwargs):
        return _Stream(
            [
                _Event({"type": "response.output_text.delta", "delta": "partial"}),
                httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
            ]
        )


class _DisconnectingResponsesOpenAI:
    def __init__(self):
        self.responses = _DisconnectingResponses()


class _FailingResponses:
    async def create(self, **kwargs):
        return _Stream(
            [
                _Event(
                    {
                        "type": "response.failed",
                        "response": {
                            "error": {
                                "type": "invalid_request_error",
                                "code": "context_length_exceeded",
                                "message": "Your input exceeds the context window of this model.",
                            }
                        },
                    }
                ),
            ]
        )


class _FailingResponsesOpenAI:
    def __init__(self):
        self.responses = _FailingResponses()


class _ChatDelta:
    content = "partial"
    tool_calls = None


class _ChatChoice:
    finish_reason = None
    delta = _ChatDelta()


class _ChatChunk:
    usage = None
    choices = [_ChatChoice()]


class _DisconnectingChatCompletions:
    async def create(self, **kwargs):
        return _Stream(
            [
                _ChatChunk(),
                httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
            ]
        )


class _DisconnectingChatOpenAI:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _DisconnectingChatCompletions()})()


@pytest.mark.asyncio
async def test_native_openai_tools_with_reasoning_use_responses_for_completion():
    client = OpenAIClient(api_key="test")
    fake = _FakeOpenAI()
    client._client = fake

    response = await client._completion(
        messages=[{"role": "user", "content": "search"}],
        model="gpt-5.5",
        tools=[{"type": "function", "function": {"name": "Search", "parameters": {"type": "object"}}}],
        tool_choice="auto",
        reasoning_effort="high",
    )

    request = fake.responses.requests[0]
    assert request["model"] == "gpt-5.5"
    assert request["store"] is False
    assert request["reasoning"] == {"effort": "high", "summary": "auto"}
    assert request["tools"][0]["name"] == "Search"
    assert response.choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_native_openai_tools_with_reasoning_use_responses_for_streaming():
    client = OpenAIClient(api_key="test")
    fake = _FakeOpenAI()
    client._client = fake

    events = [
        item
        async for item in client._stream_completion(
            messages=[{"role": "user", "content": "search"}],
            model="gpt-5.5",
            tools=[{"type": "function", "function": {"name": "Search", "parameters": {"type": "object"}}}],
            tool_choice="auto",
            reasoning_effort="high",
        )
    ]

    request = fake.responses.requests[0]
    assert "stream" not in request
    assert request["reasoning"] == {"effort": "high", "summary": "auto"}
    assert events[0] == "ok"
    assert events[-1].choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_completed_responses_call_emits_text_before_final_response():
    fake = _FakeOpenAI()

    events = [
        item
        async for item in complete_responses_completion(
            fake,
            {"model": "gpt-5.5", "input": "hi"},
            model="gpt-5.5",
        )
    ]

    assert fake.responses.requests[0] == {"model": "gpt-5.5", "input": "hi"}
    assert events[0] == "ok"
    assert events[-1].choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_buffered_responses_stream_retries_disconnect_after_upstream_delta():
    fake = _FlakyAfterDeltaOpenAI()

    events = [
        item
        async for item in buffered_stream_responses_completion(
            fake,
            {"model": "gpt-5.5", "input": "hi"},
            model="gpt-5.5",
        )
    ]

    assert fake.responses.calls == 2
    assert fake.responses.requests[0]["stream"] is True
    assert events[0] == "ok"
    assert events[-1].choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_live_responses_stream_reports_remote_protocol_disconnect():
    fake = _DisconnectingResponsesOpenAI()
    stream = stream_responses_completion(
        fake,
        {"model": "gpt-5.5", "input": "hi"},
        model="gpt-5.5",
    )

    assert await anext(stream) == "partial"
    with pytest.raises(RuntimeError, match="OpenAI response stream disconnected before completion"):
        await anext(stream)


@pytest.mark.asyncio
async def test_live_responses_stream_preserves_provider_error_code():
    from ntrp.services.chat import _safe_error

    stream = stream_responses_completion(
        _FailingResponsesOpenAI(),
        {"model": "gpt-5.5", "input": "hi"},
        model="gpt-5.5",
    )

    with pytest.raises(RuntimeError) as exc_info:
        await anext(stream)

    code, message, _debug_id = _safe_error(exc_info.value)
    assert code == "context_length_exceeded"
    assert "context window" in message


@pytest.mark.asyncio
async def test_chat_completion_stream_reports_remote_protocol_disconnect():
    client = OpenAIClient(api_key="test")
    client._client = _DisconnectingChatOpenAI()
    stream = client._stream_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-5.2",
    )

    assert await anext(stream) == "partial"
    with pytest.raises(RuntimeError, match="OpenAI chat completion stream disconnected before completion"):
        await anext(stream)


class _ToolStreamChatCompletions:
    async def create(self, **kwargs):
        def chunk(*, finish_reason=None, tool_calls=None):
            return SimpleNamespace(
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason=finish_reason,
                        delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=tool_calls),
                    )
                ],
            )

        def tool_call(*, index=0, call_id=None, name=None, arguments=None):
            return SimpleNamespace(
                index=index,
                id=call_id,
                function=SimpleNamespace(name=name, arguments=arguments),
            )

        return _Stream(
            [
                chunk(tool_calls=[tool_call(call_id="call_1", name="Search")]),
                chunk(tool_calls=[tool_call(arguments='{"q"')]),
                chunk(finish_reason="tool_calls", tool_calls=[tool_call(arguments=':"hi"}')]),
            ]
        )


class _ToolStreamChatOpenAI:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_ToolStreamChatCompletions())


@pytest.mark.asyncio
async def test_chat_completion_stream_emits_tool_call_deltas_before_final_response():
    client = OpenAIClient(api_key="test")
    client._client = _ToolStreamChatOpenAI()

    events = [
        item
        async for item in client._stream_completion(
            messages=[{"role": "user", "content": "search"}],
            model="gpt-5.2",
            tools=[{"type": "function", "function": {"name": "Search", "parameters": {"type": "object"}}}],
            tool_choice="auto",
        )
    ]

    deltas = [item for item in events if isinstance(item, ToolCallStreamDelta)]
    assert deltas == [
        ToolCallStreamDelta(index=0, tool_id="call_1", name="Search"),
        ToolCallStreamDelta(index=0, arguments_delta='{"q"'),
        ToolCallStreamDelta(index=0, arguments_delta=':"hi"}'),
        ToolCallStreamDelta(index=0, tool_id="call_1", name="Search", done=True),
    ]
    assert events[-1].choices[0].message.tool_calls[0].function.arguments == '{"q":"hi"}'


class _ToolResponse:
    status = "completed"
    usage = _Usage()
    output = [
        _FakeItem(
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "Search",
                "arguments": '{"q":"hi"}',
            }
        )
    ]


class _ToolResponses:
    async def create(self, **kwargs):
        return _Stream(
            [
                _Event(
                    {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {"type": "function_call", "call_id": "call_1", "name": "Search", "arguments": ""},
                    }
                ),
                _Event({"type": "response.function_call_arguments.delta", "output_index": 0, "delta": '{"q"'}),
                _Event({"type": "response.function_call_arguments.delta", "output_index": 0, "delta": ':"hi"}'}),
                _Event(
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "Search",
                            "arguments": '{"q":"hi"}',
                        },
                    }
                ),
                _Event({"type": "response.completed"}, response=_ToolResponse()),
            ]
        )


class _ToolResponsesOpenAI:
    def __init__(self):
        self.responses = _ToolResponses()


@pytest.mark.asyncio
async def test_responses_stream_emits_tool_call_deltas_before_final_response():
    events = [
        item
        async for item in stream_responses_completion(
            _ToolResponsesOpenAI(),
            {"model": "gpt-5.5", "input": "search"},
            model="gpt-5.5",
        )
    ]

    deltas = [item for item in events if isinstance(item, ToolCallStreamDelta)]
    assert deltas == [
        ToolCallStreamDelta(index=0, tool_id="call_1", name="Search"),
        ToolCallStreamDelta(index=0, arguments_delta='{"q"'),
        ToolCallStreamDelta(index=0, arguments_delta=':"hi"}'),
        ToolCallStreamDelta(index=0, tool_id="call_1", name="Search", done=True),
    ]
    assert events[-1].choices[0].message.tool_calls[0].function.arguments == '{"q":"hi"}'
