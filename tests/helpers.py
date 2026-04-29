"""Shared test helpers for building mock LLM responses and test fixtures."""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from ntrp.agent import Choice, CompletionResponse, FunctionCall, Message, ToolCall, Usage
from ntrp.context.models import SessionState
from ntrp.core.tool_executor import NtrpToolExecutor
from ntrp.llm.base import CompletionClient
from ntrp.tools.core import Tool
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.executor import ToolExecutor


def make_text_response(content: str, model: str = "test-model") -> CompletionResponse:
    return CompletionResponse(
        choices=[
            Choice(
                message=Message(role="assistant", content=content, tool_calls=None, reasoning_content=None),
                finish_reason="stop",
            )
        ],
        usage=Usage(),
        model=model,
    )


def make_tool_response(
    tool_name: str, arguments: dict, call_id: str | None = None, model: str = "test-model"
) -> CompletionResponse:
    return CompletionResponse(
        choices=[
            Choice(
                message=Message(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id=call_id or f"call_{tool_name}",
                            type="function",
                            function=FunctionCall(name=tool_name, arguments=json.dumps(arguments)),
                        )
                    ],
                    reasoning_content=None,
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=Usage(),
        model=model,
    )


class MockCompletionClient(CompletionClient):
    """Returns responses in sequence. Last response repeats forever."""

    def __init__(self, responses: list[CompletionResponse]):
        self._responses = responses
        self._index = 0
        self.calls: list[dict] = []

    async def _completion(self, messages, model, **kwargs) -> CompletionResponse:
        self.calls.append({"messages": messages, "model": model, **kwargs})
        resp = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return resp

    async def close(self) -> None:
        pass


def make_executor(tools: dict[str, Tool] | None = None) -> ToolExecutor:
    executor = ToolExecutor.__new__(ToolExecutor)
    executor._get_services = dict
    executor.registry = ToolRegistry()
    for name, tool in (tools or {}).items():
        executor.registry.register(name, tool)
    return executor


def make_tool_context(executor: ToolExecutor) -> ToolContext:
    return ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )


class MockLLMClient:
    """Wraps MockCompletionClient to match the LLMClient protocol."""

    def __init__(self, client: MockCompletionClient):
        self._client = client

    @property
    def calls(self):
        return self._client.calls

    async def stream(
        self, messages: list[dict], model: str, tools: list[dict], tool_choice=None
    ) -> AsyncGenerator[str | CompletionResponse]:
        async for item in self._client.stream_completion(
            model=model, messages=messages, tools=tools, tool_choice="auto"
        ):
            yield item

    async def complete(self, model: str, messages: list[dict], **kwargs) -> CompletionResponse:
        return await self._client.completion(model=model, messages=messages, **kwargs)


def make_test_executor(executor: ToolExecutor) -> NtrpToolExecutor:
    ctx = make_tool_context(executor)
    return NtrpToolExecutor(executor, ctx)
