from collections.abc import AsyncGenerator
from typing import Protocol

from ntrp.agent.types.llm import CompletionResponse
from ntrp.agent.types.tool_choice import ToolChoice


class LLMClient(Protocol):
    async def stream(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        tool_choice: ToolChoice | None = None,
    ) -> AsyncGenerator[str | CompletionResponse]: ...

    async def complete(
        self,
        model: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResponse: ...
