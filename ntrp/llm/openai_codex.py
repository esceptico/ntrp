from collections.abc import AsyncGenerator
from typing import Any

import openai
from pydantic import BaseModel

from ntrp.agent import (
    Choice,
    CompletionResponse,
    FinishReason,
    FunctionCall,
    Message,
    ReasoningContentDelta,
    Role,
    ToolCall,
    Usage,
)
from ntrp.core.content import render_context
from ntrp.llm.base import CompletionClient
from ntrp.llm.openai_codex_auth import CODEX_BASE_URL, get_valid_tokens
from ntrp.llm.utils import blocks_to_text

_MODEL_PREFIX = "openai-codex/"
_REASONING_INCLUDE = ["reasoning.encrypted_content"]


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

            stream = await client.responses.create(**request)
            text_parts: list[str] = []
            reasoning_parts: list[str] = []
            completed_items: list[dict[str, Any]] = []
            final_response = None

            async for event in stream:
                data = event.model_dump(exclude_none=True)
                event_type = data.get("type")

                if event_type == "response.output_text.delta":
                    delta = data.get("delta")
                    if isinstance(delta, str) and delta:
                        text_parts.append(delta)
                        yield delta
                    continue

                if event_type in ("response.reasoning_text.delta", "response.reasoning_summary_text.delta"):
                    delta = data.get("delta")
                    if isinstance(delta, str) and delta:
                        reasoning_parts.append(delta)
                        yield ReasoningContentDelta(delta)
                    continue

                if event_type == "response.completed":
                    final_response = event.response
                    continue

                if event_type == "response.output_item.done":
                    item = data.get("item")
                    if isinstance(item, dict):
                        completed_items.append(item)
                    continue

                if event_type in ("response.failed", "response.incomplete"):
                    response = data.get("response")
                    error = response.get("error") if isinstance(response, dict) else None
                    message = error.get("message") if isinstance(error, dict) else None
                    raise RuntimeError(message or f"OpenAI Codex response failed: {event_type}")

                if event_type == "error":
                    error = data.get("error")
                    if isinstance(error, dict) and isinstance(error.get("message"), str):
                        raise RuntimeError(error["message"])
                    raise RuntimeError("OpenAI Codex stream returned an error")

            if final_response is not None:
                parsed = self._parse_response(final_response, model, completed_items or None)
                if parsed.choices:
                    msg = parsed.choices[0].message
                    content = msg.content or ("".join(text_parts) or None)
                    reasoning_content = msg.reasoning_content or ("".join(reasoning_parts) or None)
                    if content != msg.content or reasoning_content != msg.reasoning_content:
                        parsed.choices[0] = Choice(
                            message=Message(
                                role=msg.role,
                                content=content,
                                tool_calls=msg.tool_calls,
                                reasoning_content=reasoning_content,
                                reasoning_encrypted_content=msg.reasoning_encrypted_content,
                            ),
                            finish_reason=parsed.choices[0].finish_reason,
                        )
                yield parsed
                return

            yield CompletionResponse(
                choices=[
                    Choice(
                        message=Message(
                            role=Role.ASSISTANT,
                            content="".join(text_parts) or None,
                            tool_calls=None,
                            reasoning_content="".join(reasoning_parts) or None,
                        ),
                        finish_reason=FinishReason.STOP,
                    )
                ],
                usage=Usage(),
                model=model,
            )
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
        instructions, input_items = self._convert_messages(messages)
        request: dict[str, Any] = {
            "model": self._api_model(model),
            "input": input_items,
            "include": _REASONING_INCLUDE,
            "store": False,
        }
        if instructions:
            request["instructions"] = instructions
        if tools:
            request["tools"] = [self._convert_tool(tool) for tool in tools]
            request["tool_choice"] = self._convert_tool_choice(tool_choice)
        if temperature is not None:
            request["temperature"] = temperature
        # The ChatGPT Codex endpoint rejects max_output_tokens even though public Responses accepts it.
        _ = max_tokens
        if reasoning_effort is not None:
            request["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}
        if response_format is not None:
            request["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": response_format.__name__,
                    "schema": response_format.model_json_schema(),
                    "strict": False,
                }
            }
        if prompt_cache_key := kwargs.get("prompt_cache_key"):
            request["prompt_cache_key"] = prompt_cache_key
        if extra_body := kwargs.get("extra_body"):
            request["extra_body"] = dict(extra_body)
        return request

    def _api_model(self, model: str) -> str:
        return model.removeprefix(_MODEL_PREFIX)

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[dict[str, Any]]]:
        instructions: list[str] = []
        input_items: list[dict[str, Any]] = []

        for msg in messages:
            role = msg["role"]
            content = msg.get("content") or ""

            if role == Role.SYSTEM or role == "system":
                instructions.append(self._content_to_text(content))
                continue

            if role == Role.USER or role == "user":
                input_items.append({"role": "user", "content": self._convert_user_content(content)})
                continue

            if role == Role.ASSISTANT or role == "assistant":
                input_items.extend(self._convert_assistant_message(msg))
                continue

            if role == Role.TOOL or role == "tool":
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg["tool_call_id"],
                        "output": self._content_to_text(content),
                    }
                )

        return ("\n\n".join(part for part in instructions if part) or None), input_items

    def _content_to_text(self, content: str | list) -> str:
        if isinstance(content, str):
            return content
        return blocks_to_text(content)

    def _convert_user_content(self, content: str | list) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return content
        result: list[dict[str, Any]] = []
        for block in content:
            match block.get("type"):
                case "text":
                    result.append({"type": "input_text", "text": block["text"]})
                case "image":
                    result.append(
                        {
                            "type": "input_image",
                            "detail": "auto",
                            "image_url": f"data:{block['media_type']};base64,{block['data']}",
                        }
                    )
                case "context":
                    result.append({"type": "input_text", "text": render_context(block)})
        return result

    def _convert_assistant_message(self, msg: dict) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if encrypted := msg.get("reasoning_encrypted_content"):
            items.append({"type": "reasoning", "encrypted_content": encrypted, "summary": []})
        if content := msg.get("content"):
            items.append({"role": "assistant", "content": self._content_to_text(content)})
        for tc in msg.get("tool_calls", []):
            fn = tc["function"]
            items.append(
                {
                    "type": "function_call",
                    "call_id": tc["id"],
                    "name": fn["name"],
                    "arguments": fn.get("arguments", "{}"),
                    "status": "completed",
                }
            )
        return items

    def _convert_tool(self, tool: dict) -> dict[str, Any]:
        fn = tool.get("function", tool)
        return {
            "type": "function",
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            "strict": False,
        }

    def _convert_tool_choice(self, tool_choice: str | dict | None) -> str | dict[str, str]:
        if tool_choice in (None, "auto"):
            return "auto"
        if tool_choice in ("none", "required"):
            return tool_choice
        if isinstance(tool_choice, dict):
            fn = tool_choice.get("function")
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                return {"type": "function", "name": fn["name"]}
        return "auto"

    def _parse_response(
        self,
        response,
        model: str,
        output_items: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        reasoning_encrypted_content = None
        tool_calls: list[ToolCall] = []

        for item in output_items if output_items is not None else response.output:
            data = item if isinstance(item, dict) else item.model_dump(exclude_none=True)
            item_type = data.get("type")
            if item_type == "message":
                for part in data.get("content", []):
                    if part.get("type") == "output_text":
                        content_parts.append(part.get("text", ""))
                    elif part.get("type") == "refusal":
                        content_parts.append(part.get("refusal", ""))
                continue

            if item_type == "reasoning":
                if encrypted := data.get("encrypted_content"):
                    reasoning_encrypted_content = encrypted
                for part in data.get("content") or []:
                    if part.get("type") == "reasoning_text":
                        reasoning_parts.append(part.get("text", ""))
                if not reasoning_parts:
                    for part in data.get("summary") or []:
                        if part.get("type") == "summary_text":
                            reasoning_parts.append(part.get("text", ""))
                continue

            if item_type == "function_call":
                call_id = data["call_id"]
                tool_calls.append(
                    ToolCall(
                        id=call_id,
                        type="function",
                        function=FunctionCall(name=data["name"], arguments=data.get("arguments", "{}")),
                    )
                )

        message = Message(
            role=Role.ASSISTANT,
            content="".join(content_parts) or None,
            tool_calls=tool_calls or None,
            reasoning_content="".join(reasoning_parts) or None,
            reasoning_encrypted_content=reasoning_encrypted_content,
        )
        return CompletionResponse(
            choices=[Choice(message=message, finish_reason=self._finish_reason(response, tool_calls))],
            usage=self._usage(response),
            model=model,
        )

    def _finish_reason(self, response, tool_calls: list[ToolCall]) -> FinishReason:
        if tool_calls:
            return FinishReason.TOOL_CALLS
        if response.status == "incomplete":
            return FinishReason.LENGTH
        return FinishReason.STOP

    def _usage(self, response) -> Usage:
        if response.usage is None:
            return Usage()
        usage = response.usage
        cache_read = usage.input_tokens_details.cached_tokens if usage.input_tokens_details else 0
        return Usage(
            prompt_tokens=usage.input_tokens - cache_read,
            completion_tokens=usage.output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=0,
        )
