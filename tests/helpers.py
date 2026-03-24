"""Shared test helpers for building mock LLM responses and test fixtures."""

import json

from ntrp.llm.base import CompletionClient
from ntrp.llm.types import Choice, CompletionResponse, FunctionCall, Message, ToolCall
from ntrp.usage import Usage


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
