from ntrp.agent import Choice, CompletionResponse, Message, Usage
from ntrp.llm.base import CompletionClient
from ntrp.observability.langfuse import LangfuseTracer, _mask


class FakeObservation:
    def __init__(self, calls: list[dict], *, name: str, as_type: str, **kwargs):
        self.calls = calls
        self.name = name
        self.as_type = as_type
        self.kwargs = kwargs

    def __enter__(self):
        self.calls.append({"event": "start", "name": self.name, "as_type": self.as_type, **self.kwargs})
        return self

    def __exit__(self, exc_type, exc, tb):
        self.calls.append({"event": "end", "name": self.name, "error": str(exc) if exc else None})

    def update(self, **kwargs):
        self.calls.append({"event": "update", "name": self.name, **kwargs})


class FakeContext:
    def __init__(self, calls: list[dict], event: str, **kwargs):
        self.calls = calls
        self.event = event
        self.kwargs = kwargs

    def __enter__(self):
        self.calls.append({"event": self.event, **self.kwargs})
        return self

    def __exit__(self, exc_type, exc, tb):
        self.calls.append({"event": f"{self.event}.end"})


class FakeTracer:
    def __init__(self):
        self.calls: list[dict] = []

    def observation(self, *, name: str, as_type: str = "span", **kwargs):
        return FakeObservation(self.calls, name=name, as_type=as_type, **kwargs)


class FakeCompletionClient(CompletionClient):
    def __init__(self):
        self.kwargs: dict | None = None

    async def _stream_completion(self, **kwargs):
        self.kwargs = kwargs
        yield "hello"
        yield _response("hello", prompt=11, completion=7)

    async def _completion(self, **kwargs):
        self.kwargs = kwargs
        return _response("done", prompt=3, completion=5)

    async def close(self) -> None:
        pass


def _response(text: str, *, prompt: int, completion: int) -> CompletionResponse:
    return CompletionResponse(
        choices=[
            Choice(
                message=Message(role="assistant", content=text, tool_calls=None, reasoning_content=None),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=prompt, completion_tokens=completion),
        model="test-model",
    )


async def test_stream_traces_generation(monkeypatch):
    tracer = FakeTracer()
    monkeypatch.setattr("ntrp.llm.base.get_langfuse_tracer", lambda: tracer)
    client = FakeCompletionClient()

    items = [item async for item in client.stream_completion(messages=[{"role": "user", "content": "hi"}], model="m", tools=[])]

    assert items[0] == "hello"
    assert any(call["event"] == "start" and call["name"] == "llm.stream" for call in tracer.calls)
    assert any(
        call["event"] == "update"
        and call["name"] == "llm.stream"
        and call["output"] == "hello"
        and call["usage_details"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
        for call in tracer.calls
    )


async def test_complete_traces_generation(monkeypatch):
    tracer = FakeTracer()
    monkeypatch.setattr("ntrp.llm.base.get_langfuse_tracer", lambda: tracer)
    client = FakeCompletionClient()

    response = await client.completion(model="m", messages=[{"role": "user", "content": "hi"}])

    assert response.choices[0].message.content == "done"
    assert any(call["event"] == "start" and call["name"] == "llm.completion" for call in tracer.calls)
    assert any(
        call["event"] == "update"
        and call["name"] == "llm.completion"
        and call["usage_details"] == {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}
        for call in tracer.calls
    )


async def test_completion_uses_semantic_name_without_leaking_trace_kwargs(monkeypatch):
    tracer = FakeTracer()
    monkeypatch.setattr("ntrp.llm.base.get_langfuse_tracer", lambda: tracer)
    client = FakeCompletionClient()

    await client.completion(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        langfuse_name="memory.curate",
        langfuse_metadata={"scope": "test"},
    )

    assert any(
        call["event"] == "start"
        and call["name"] == "memory.curate"
        and call["metadata"]["scope"] == "test"
        for call in tracer.calls
    )
    assert "langfuse_name" not in client.kwargs
    assert "langfuse_metadata" not in client.kwargs


def test_langfuse_mask_accepts_sdk_signature():
    masked = _mask(
        data={
            "authorization": "Bearer abc123",
            "nested": {"api_key": "sk-lf-secret-value"},
            "content": "token sk-testsecret123456",
        }
    )

    assert masked == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]"},
        "content": "token [REDACTED]",
    }


def test_trace_propagates_langfuse_attributes(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    class FakeClient:
        def propagate_attributes(self, **kwargs):
            return FakeContext(calls, "propagate", **kwargs)

        def start_as_current_observation(self, **kwargs):
            return FakeObservation(calls, **kwargs)

    tracer = LangfuseTracer()
    tracer._loaded = True
    tracer._client = FakeClient()

    with tracer.trace(
        name="chat:My Session",
        session_id="session-1",
        metadata={"run_id": "run-1"},
        tags=["chat"],
        input={"latest_user_message": "hi"},
    ) as span:
        span.update(output="done")

    assert any(
        call["event"] == "propagate"
        and call["trace_name"] == "chat:My Session"
        and call["session_id"] == "session-1"
        for call in calls
    )
    assert any(call["event"] == "start" and call["name"] == "chat:My Session" for call in calls)


def test_trace_sanitizes_name_and_propagated_metadata(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    class FakeClient:
        def propagate_attributes(self, **kwargs):
            return FakeContext(calls, "propagate", **kwargs)

        def start_as_current_observation(self, **kwargs):
            return FakeObservation(calls, **kwargs)

    tracer = LangfuseTracer()
    tracer._loaded = True
    tracer._client = FakeClient()

    with tracer.trace(
        name="chat:привет" + ("x" * 250),
        metadata={"ok": True, "skip": None},
    ):
        pass

    propagate = next(call for call in calls if call["event"] == "propagate")
    assert propagate["trace_name"].startswith("chat:")
    assert len(propagate["trace_name"]) == 200
    assert propagate["metadata"] == {"ok": "True"}
