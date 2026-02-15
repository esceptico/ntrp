from abc import ABC, abstractmethod

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
