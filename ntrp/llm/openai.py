import openai

from pydantic import BaseModel

from ntrp.llm.base import CompletionClient, EmbeddingClient
from ntrp.llm.utils import blocks_to_text
from ntrp.llm.types import (
    Choice,
    CompletionResponse,
    FunctionCall,
    Message,
    ToolCall,
    Usage,
)


class OpenAIClient(CompletionClient, EmbeddingClient):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

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

        response = await self._client.chat.completions.create(**request)
        return self._parse_response(response, model)

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
        return [
            {**msg, "content": blocks_to_text(msg["content"])} if msg.get("role") == "system" and isinstance(msg.get("content"), list) else msg
            for msg in messages
        ]

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

        message = Message(
            role=msg.role,
            content=msg.content,
            tool_calls=tool_calls,
            reasoning_content=msg.reasoning_content,
        )

        return CompletionResponse(
            choices=[Choice(message=message, finish_reason=choice.finish_reason)],
            usage=usage,
            model=model,
        )
