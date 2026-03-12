from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from pydantic import BaseModel

from ntrp.llm.retry import with_retry
from ntrp.llm.types import CompletionResponse


class CompletionClient(ABC):
    @abstractmethod
    async def _completion(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs,
    ) -> CompletionResponse: ...

    async def completion(self, **kwargs) -> CompletionResponse:
        return await with_retry(self._completion, **kwargs)

    async def _stream_completion(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs,
    ) -> AsyncGenerator[str | CompletionResponse]:
        """Yield text deltas, then the final CompletionResponse.

        Default: non-streaming fallback.
        """
        response = await self._completion(
            messages=messages, model=model, tools=tools,
            tool_choice=tool_choice, temperature=temperature,
            max_tokens=max_tokens, response_format=response_format, **kwargs,
        )
        text = response.choices[0].message.content if response.choices else None
        if text:
            yield text
        yield response

    async def stream_completion(self, **kwargs) -> AsyncGenerator[str | CompletionResponse]:
        async for item in self._stream_completion(**kwargs):
            yield item

    @abstractmethod
    async def close(self) -> None: ...


class EmbeddingClient(ABC):
    @abstractmethod
    async def _embedding(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]: ...

    async def embedding(self, **kwargs) -> list[list[float]]:
        return await with_retry(self._embedding, **kwargs)

    @abstractmethod
    async def close(self) -> None: ...
