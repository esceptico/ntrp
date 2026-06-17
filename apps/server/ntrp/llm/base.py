from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from pydantic import BaseModel

from ntrp.agent.types.llm import CompletionResponse, ReasoningContentDelta, ToolCallStreamDelta
from ntrp.llm.models import get_model
from ntrp.llm.retry import with_retry
from ntrp.observability import get_langfuse_tracer


def _response_output(response: CompletionResponse) -> str | None:
    return response.choices[0].message.content if response.choices else None


def _update_generation(generation, response: CompletionResponse) -> None:
    if generation is None:
        return
    usage = response.usage
    generation.update(
        output=_response_output(response),
        usage_details={
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        },
        metadata={"model": response.model},
    )


def _model_parameters(kwargs: dict) -> dict:
    response_format = kwargs.get("response_format")
    return {
        "temperature": kwargs.get("temperature"),
        "max_tokens": kwargs.get("max_tokens"),
        "tool_choice": kwargs.get("tool_choice"),
        "reasoning_effort": kwargs.get("reasoning_effort"),
        "response_format": response_format.__name__ if response_format is not None else None,
        "tools": [tool.get("function", {}).get("name") for tool in kwargs.get("tools") or []],
    }


def _model_metadata(model_id: str | None, operation: str) -> dict:
    metadata = {"operation": operation}
    if not model_id:
        return metadata
    try:
        model = get_model(model_id)
        metadata["provider"] = model.provider.value
    except Exception:
        metadata["provider"] = "unknown"
    metadata["model"] = model_id
    return metadata


def _tracing_options(kwargs: dict, default_name: str, operation: str) -> tuple[dict, str, dict | None]:
    provider_kwargs = dict(kwargs)
    name = provider_kwargs.pop("langfuse_name", None) or default_name
    extra_metadata = provider_kwargs.pop("langfuse_metadata", None)
    metadata = _model_metadata(provider_kwargs.get("model"), operation)
    if extra_metadata:
        metadata.update(extra_metadata)
    return provider_kwargs, name, metadata


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
        reasoning_effort: str | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs,
    ) -> CompletionResponse: ...

    async def completion(self, **kwargs) -> CompletionResponse:
        kwargs, name, metadata = _tracing_options(kwargs, "llm.completion", "complete")
        model = kwargs.get("model")
        with get_langfuse_tracer().observation(
            name=name,
            as_type="generation",
            model=model,
            input=kwargs.get("messages"),
            model_parameters=_model_parameters(kwargs),
            metadata=metadata,
        ) as generation:
            response = await with_retry(self._completion, **kwargs)
            _update_generation(generation, response)
            return response

    async def _stream_completion(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs,
    ) -> AsyncGenerator[str | ReasoningContentDelta | ToolCallStreamDelta | CompletionResponse]:
        """Yield text deltas, then the final CompletionResponse.

        Default: non-streaming fallback.
        """
        response = await self._completion(
            messages=messages,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            response_format=response_format,
            **kwargs,
        )
        text = response.choices[0].message.content if response.choices else None
        if text:
            yield text
        yield response

    async def stream_completion(self, **kwargs) -> AsyncGenerator[str | ReasoningContentDelta | ToolCallStreamDelta | CompletionResponse]:
        kwargs, name, metadata = _tracing_options(kwargs, "llm.stream", "stream")
        model = kwargs.get("model")
        with get_langfuse_tracer().observation(
            name=name,
            as_type="generation",
            model=model,
            input=kwargs.get("messages"),
            model_parameters=_model_parameters(kwargs),
            metadata=metadata,
        ) as generation:
            async for item in self._stream_completion(**kwargs):
                if isinstance(item, CompletionResponse):
                    _update_generation(generation, item)
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
