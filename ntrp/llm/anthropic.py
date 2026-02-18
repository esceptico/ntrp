import json

import anthropic
from pydantic import BaseModel

from ntrp.llm.base import CompletionClient
from ntrp.llm.models import get_model
from ntrp.llm.types import (
    Choice,
    CompletionResponse,
    FunctionCall,
    Message,
    ToolCall,
    Usage,
)
from ntrp.llm.utils import blocks_to_text, parse_args

_FINISH_REASONS = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "stop_sequence": "stop",
}


class AnthropicClient(CompletionClient):
    def __init__(self, api_key: str | None = None):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

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
        if max_tokens is None:
            max_tokens = get_model(model).max_output_tokens

        system, api_messages = self._split_system(messages)
        api_messages = self._convert_messages(api_messages)
        api_tools = self._convert_tools(tools) if tools else None
        api_tool_choice = self._resolve_tool_choice(api_tools, tool_choice, response_format)

        # Structured output via tool-use trick
        if response_format is not None:
            api_tools = api_tools or []
            api_tools.append(self._make_schema_tool(response_format))

        # Inject cache_control on last tool and last user message
        if api_tools:
            api_tools[-1]["cache_control"] = {"type": "ephemeral"}
        self._inject_cache_control_last_message(api_messages)

        request = self._build_request(
            model=model,
            messages=api_messages,
            system=system,
            tools=api_tools,
            tool_choice=api_tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        response = await self._client.messages.create(**request)
        return self._parse_response(response, model, response_format)

    async def close(self) -> None:
        await self._client.close()

    # --- Request building ---

    def _resolve_tool_choice(
        self,
        tools: list[dict] | None,
        tool_choice: str | None,
        response_format: type[BaseModel] | None,
    ) -> dict | None:
        if response_format is not None:
            return {"type": "tool", "name": "_structured_output"}
        if tool_choice == "auto" and tools:
            return {"type": "auto"}
        return None

    def _build_request(
        self,
        *,
        model: str,
        messages: list[dict],
        system: list[dict] | None,
        tools: list[dict] | None,
        tool_choice: dict | None,
        temperature: float | None,
        max_tokens: int | None,
        **kwargs,
    ) -> dict:
        request: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        optional = {
            "system": system,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        request.update({k: v for k, v in optional.items() if v is not None})
        if extra := kwargs.get("extra_body"):
            request.update(extra)
        return request

    # --- Message conversion ---

    def _split_system(self, messages: list[dict]) -> tuple[list[dict] | None, list[dict]]:
        if not messages or messages[0].get("role") != "system":
            return None, messages

        content = messages[0]["content"]
        system = content if isinstance(content, list) else [{"type": "text", "text": blocks_to_text(content)}]

        return system, messages[1:]

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        result: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "assistant":
                result.append(self._convert_assistant(msg))
            elif role == "tool":
                self._append_tool_result(result, msg)
            elif role == "user":
                result.append({"role": "user", "content": msg["content"]})
        return result

    def _convert_assistant(self, msg: dict) -> dict:
        content_blocks: list[dict] = []
        if text := msg["content"]:
            content_blocks.append({"type": "text", "text": text})

        for tc in msg.get("tool_calls", []):
            fn = tc["function"]
            content_blocks.append(
                {
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": fn["name"],
                    "input": parse_args(fn.get("arguments", "{}")),
                }
            )

        return {"role": "assistant", "content": content_blocks or ""}

    def _append_tool_result(self, result: list[dict], msg: dict) -> None:
        block = {
            "type": "tool_result",
            "tool_use_id": msg["tool_call_id"],
            "content": msg["content"],
        }
        # Merge consecutive tool results into one user message
        if result and result[-1]["role"] == "user" and isinstance(result[-1]["content"], list):
            last_types = {b.get("type") for b in result[-1]["content"] if isinstance(b, dict)}
            if "tool_result" in last_types:
                result[-1]["content"].append(block)
                return
        result.append({"role": "user", "content": [block]})

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "name": (fn := tool.get("function", tool))["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            }
            for tool in tools
        ]

    def _make_schema_tool(self, model_class: type[BaseModel]) -> dict:
        return {
            "name": "_structured_output",
            "description": f"Return structured output as {model_class.__name__}",
            "input_schema": model_class.model_json_schema(),
        }

    def _inject_cache_control_last_message(self, messages: list[dict]) -> None:
        if not messages:
            return
        last = messages[-1]
        content = last.get("content")
        if isinstance(content, str):
            last["content"] = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
        elif isinstance(content, list) and content:
            content[-1]["cache_control"] = {"type": "ephemeral"}

    # --- Response parsing ---

    def _parse_response(self, response, model: str, response_format: type[BaseModel] | None) -> CompletionResponse:
        content, tool_calls, reasoning = self._parse_content_blocks(response.content, response_format)
        usage = self._parse_usage(response.usage)

        message = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls or None,
            reasoning_content=reasoning,
        )

        return CompletionResponse(
            choices=[
                Choice(
                    message=message,
                    finish_reason=_FINISH_REASONS.get(response.stop_reason, response.stop_reason),
                )
            ],
            usage=usage,
            model=model,
        )

    def _parse_content_blocks(
        self,
        blocks,
        response_format: type[BaseModel] | None,
    ) -> tuple[str | None, list[ToolCall], str | None]:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        reasoning = None

        for block in blocks:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                if response_format and block.name == "_structured_output":
                    text_parts.append(json.dumps(block.input))
                else:
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            type="function",
                            function=FunctionCall(
                                name=block.name,
                                arguments=json.dumps(block.input),
                            ),
                        )
                    )
            elif block.type == "thinking":
                reasoning = block.thinking

        content = "\n".join(text_parts) if text_parts else None
        return content, tool_calls, reasoning

    def _parse_usage(self, usage) -> Usage:
        return Usage(
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
        )
