from collections.abc import AsyncGenerator
from typing import Protocol

from ntrp.agent.types.llm import CompletionResponse, ReasoningContentDelta
from ntrp.agent.types.tool_choice import ToolChoice


class LLMClient(Protocol):
    async def stream(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        tool_choice: ToolChoice | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncGenerator[str | ReasoningContentDelta | CompletionResponse]: ...

    async def complete(
        self,
        model: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResponse: ...
