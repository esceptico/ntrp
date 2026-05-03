import pytest

from ntrp.llm.openai import OpenAIClient


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
    def __init__(self, events: list[_Event]):
        self._events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration:
            raise StopAsyncIteration


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


class _FakeChatCompletions:
    async def create(self, **kwargs):
        raise AssertionError("chat completions should not be used")


class _FakeOpenAI:
    def __init__(self):
        self.responses = _FakeResponses()
        self.chat = type("Chat", (), {"completions": _FakeChatCompletions()})()


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
    assert request["stream"] is True
    assert request["reasoning"] == {"effort": "high", "summary": "auto"}
    assert events[0] == "ok"
