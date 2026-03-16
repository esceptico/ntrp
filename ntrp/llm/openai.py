from collections.abc import AsyncGenerator

import openai
from pydantic import BaseModel

from ntrp.llm.base import CompletionClient, EmbeddingClient
from ntrp.llm.types import (
    Choice,
    CompletionResponse,
    FunctionCall,
    Message,
    ToolCall,
    Usage,
)
from ntrp.llm.utils import blocks_to_text


class OpenAIClient(CompletionClient, EmbeddingClient):
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 60.0):
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def _prepare(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
        tool_choice: str | None,
        temperature: float | None,
        max_tokens: int | None,
        response_format: type[BaseModel] | None,
        **kwargs,
    ) -> dict:
        messages = self._preprocess_messages(messages)
        request: dict = {"model": model, "messages": messages}

        optional = {
            "tools": tools,
            "tool_choice": tool_choice if tools else None,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request.update({k: v for k, v in optional.items() if v is not None})

        if response_format is not None:
            schema = response_format.model_json_schema()
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_format.__name__,
                    "schema": schema,
                    "strict": False,
                },
            }

        if extra := kwargs.get("extra_body"):
            request["extra_body"] = extra

        return request

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
    ) -> CompletionResponse:
        request = self._prepare(
            messages,
            model,
            tools,
            tool_choice,
            temperature,
            max_tokens,
            response_format,
            **kwargs,
        )
        response = await self._client.chat.completions.create(**request)
        return self._parse_response(response, model)

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
        request = self._prepare(
            messages,
            model,
            tools,
            tool_choice,
            temperature,
            max_tokens,
            response_format,
            **kwargs,
        )
        request["stream"] = True
        request["stream_options"] = {"include_usage": True}

        stream = await self._client.chat.completions.create(**request)

        content_parts: list[str] = []
        tool_call_chunks: dict[int, dict] = {}
        finish_reason = "stop"
        usage_chunk = None
        reasoning_parts: list[str] = []

        async for chunk in stream:
            if chunk.usage:
                usage_chunk = chunk.usage
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta

            if delta.content:
                yield delta.content
                content_parts.append(delta.content)

            if rc := getattr(delta, "reasoning_content", None):
                reasoning_parts.append(rc)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.index not in tool_call_chunks:
                        tool_call_chunks[tc.index] = {"id": "", "name": "", "arguments": ""}
                    entry = tool_call_chunks[tc.index]
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            entry["name"] = tc.function.name
                        if tc.function.arguments:
                            entry["arguments"] += tc.function.arguments

        content = "".join(content_parts) or None
        tool_calls = None
        if tool_call_chunks:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    type="function",
                    function=FunctionCall(name=tc["name"], arguments=tc["arguments"]),
                )
                for _, tc in sorted(tool_call_chunks.items())
            ]

        if usage_chunk:
            details = getattr(usage_chunk, "prompt_tokens_details", None)
            cache_read = (details.cached_tokens or 0) if details else 0
            usage = Usage(
                prompt_tokens=usage_chunk.prompt_tokens - cache_read,
                completion_tokens=usage_chunk.completion_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=0,
            )
        else:
            usage = Usage(prompt_tokens=0, completion_tokens=0, cache_read_tokens=0, cache_write_tokens=0)

        reasoning = "".join(reasoning_parts) if reasoning_parts else None

        message = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            reasoning_content=reasoning,
        )

        yield CompletionResponse(
            choices=[Choice(message=message, finish_reason=finish_reason)],
            usage=usage,
            model=model,
        )

    async def _embedding(self, texts: list[str], model: str) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=model,
            input=texts,
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    async def close(self) -> None:
        await self._client.close()

    def _preprocess_messages(self, messages: list[dict]) -> list[dict]:
        result = []
        for msg in messages:
            content = msg["content"]
            if not isinstance(content, list):
                result.append(msg)
            elif msg["role"] == "system":
                result.append({**msg, "content": blocks_to_text(content)})
            elif msg["role"] == "user":
                result.append({**msg, "content": self._convert_user_content(content)})
            else:
                result.append(msg)
        return result

    def _convert_user_content(self, content: list) -> list[dict]:
        result = []
        for block in content:
            match block.get("type"):
                case "text":
                    result.append({"type": "text", "text": block["text"]})
                case "image":
                    result.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{block['media_type']};base64,{block['data']}"},
                        }
                    )
        return result

    def _parse_response(self, response, model: str) -> CompletionResponse:
        choice = response.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    type=tc.type,
                    function=FunctionCall(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ),
                )
                for tc in msg.tool_calls
            ]

        details = response.usage.prompt_tokens_details
        cache_read = (details.cached_tokens or 0) if details else 0

        usage = Usage(
            prompt_tokens=response.usage.prompt_tokens - cache_read,
            completion_tokens=response.usage.completion_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=0,
        )

        reasoning_content = getattr(msg, "reasoning_content", None)
        if reasoning_content is None:
            extra = getattr(msg, "model_extra", None) or {}
            reasoning_content = extra.get("reasoning_content")

        message = Message(
            role=msg.role,
            content=msg.content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
        )

        return CompletionResponse(
            choices=[Choice(message=message, finish_reason=choice.finish_reason)],
            usage=usage,
            model=model,
        )
