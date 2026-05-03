from collections.abc import AsyncGenerator
from typing import Any

import openai
from pydantic import BaseModel

from ntrp.agent import (
    CompletionResponse,
    ReasoningContentDelta,
)
from ntrp.llm.base import CompletionClient
from ntrp.llm.openai_codex_auth import CODEX_BASE_URL, get_valid_tokens
from ntrp.llm.openai_responses import (
    parse_responses_response,
    prepare_responses_request,
    stream_responses_completion,
)

_MODEL_PREFIX = "openai-codex/"


class OpenAICodexClient(CompletionClient):
    def __init__(self, timeout: float = 60.0):
        self._timeout = timeout

    async def _completion(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs,
    ) -> CompletionResponse:
        final_response: CompletionResponse | None = None
        async for event in self._stream_completion(
            messages=messages,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            response_format=response_format,
            **kwargs,
        ):
            if isinstance(event, CompletionResponse):
                final_response = event
        if final_response is None:
            raise RuntimeError("OpenAI Codex stream ended without a final response")
        return final_response

    async def _stream_completion(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs,
    ) -> AsyncGenerator[str | ReasoningContentDelta | CompletionResponse]:
        client = await self._client()
        try:
            request = self._prepare(
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
            request["stream"] = True

            async for item in stream_responses_completion(client, request, model=model):
                yield item
        finally:
            await client.close()

    async def close(self) -> None:
        return None

    async def _client(self) -> openai.AsyncOpenAI:
        tokens = await get_valid_tokens()
        headers = {
            "originator": "ntrp",
            "User-Agent": "ntrp",
        }
        if tokens.account_id:
            headers["ChatGPT-Account-Id"] = tokens.account_id
        return openai.AsyncOpenAI(
            api_key=tokens.access,
            base_url=CODEX_BASE_URL,
            timeout=self._timeout,
            default_headers=headers,
        )

    def _prepare(
        self,
        *,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
        tool_choice: str | dict | None,
        temperature: float | None,
        max_tokens: int | None,
        reasoning_effort: str | None,
        response_format: type[BaseModel] | None,
        **kwargs,
    ) -> dict[str, Any]:
        return prepare_responses_request(
            messages=messages,
            model=self._api_model(model),
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            response_format=response_format,
            allow_sampling_options=False,
            store=False,
            **kwargs,
        )

    def _api_model(self, model: str) -> str:
        return model.removeprefix(_MODEL_PREFIX)

    def _parse_response(
        self,
        response,
        model: str,
        output_items: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        return parse_responses_response(response, model, output_items)
