import copy
import json
from itertools import count

from google import genai
from google.genai import types
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
from ntrp.llm.utils import blocks_to_text, parse_args


class GeminiClient(CompletionClient, EmbeddingClient):
    def __init__(self, api_key: str | None = None):
        self._client = genai.Client(api_key=api_key)

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
        system_instruction, contents = self._convert_messages(messages)

        config_kwargs: dict = {}
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens

        if response_format is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_format

        if tools:
            config_kwargs["tools"] = self._convert_tools(tools)
            if tool_choice == "auto":
                config_kwargs["tool_config"] = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="AUTO")
                )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            **config_kwargs,
        )

        response = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        return self._parse_response(response, model)

    async def _embedding(self, texts: list[str], model: str) -> list[list[float]]:
        result = await self._client.aio.models.embed_content(
            model=model,
            contents=texts,
        )
        return [e.values for e in result.embeddings]

    async def close(self) -> None:
        pass  # google-genai client doesn't need explicit cleanup

    # --- Message conversion ---

    def _build_tool_name_map(self, messages: list[dict]) -> dict[str, str]:
        name_map: dict[str, str] = {}
        for msg in messages:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function", tc)
                    tc_id = tc.get("id", "")
                    if tc_id:
                        name_map[tc_id] = fn.get("name", "unknown")
        return name_map

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[types.Content]]:
        system_instruction = None
        contents: list[types.Content] = []
        tool_name_map = self._build_tool_name_map(messages)

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                system_instruction = blocks_to_text(msg.get("content", ""))
            elif role == "user":
                contents.append(self._convert_user(msg))
            elif role == "assistant":
                if content := self._convert_assistant(msg):
                    contents.append(content)
            elif role == "tool":
                part = self._convert_tool_result(msg, tool_name_map)
                self._append_tool_part(contents, part)

        return system_instruction, contents

    def _convert_user(self, msg: dict) -> types.Content:
        text = blocks_to_text(msg.get("content", ""))
        return types.Content(role="user", parts=[types.Part(text=text)])

    def _convert_assistant(self, msg: dict) -> types.Content | None:
        parts: list[types.Part] = []
        if text := msg.get("content"):
            parts.append(types.Part(text=text))
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", tc)
            parts.append(
                types.Part(
                    function_call=types.FunctionCall(
                        name=fn.get("name", ""),
                        args=parse_args(fn.get("arguments", "{}")),
                    )
                )
            )
        return types.Content(role="model", parts=parts) if parts else None

    def _convert_tool_result(self, msg: dict, tool_name_map: dict[str, str]) -> types.Part:
        tool_call_id = msg.get("tool_call_id", "")
        tool_name = tool_name_map.get(tool_call_id, "unknown")
        content_str = msg.get("content", "")
        try:
            result_dict = json.loads(content_str)
        except (json.JSONDecodeError, TypeError):
            result_dict = {"result": content_str}

        return types.Part(
            function_response=types.FunctionResponse(
                name=tool_name,
                response=result_dict,
            )
        )

    def _append_tool_part(self, contents: list[types.Content], part: types.Part) -> None:
        if contents and contents[-1].role == "user":
            last_parts = contents[-1].parts
            if last_parts and any(p.function_response for p in last_parts):
                contents[-1].parts.append(part)
                return
        contents.append(types.Content(role="user", parts=[part]))

    # --- Tool schema ---

    def _convert_tools(self, tools: list[dict]) -> list[types.Tool]:
        declarations = []
        for tool in tools:
            fn = tool.get("function", tool)
            params = fn.get("parameters")
            if params:
                params = self._clean_schema(params)
            declarations.append(
                types.FunctionDeclaration(
                    name=fn["name"],
                    description=fn.get("description", ""),
                    parameters=params,
                )
            )
        return [types.Tool(function_declarations=declarations)]

    def _clean_schema(self, schema: dict) -> dict:
        schema = copy.deepcopy(schema)
        self._clean_schema_recursive(schema)
        return schema

    def _clean_schema_recursive(self, schema: dict) -> None:
        for key in (
            "default",
            "exclusiveMaximum",
            "exclusiveMinimum",
            "additionalProperties",
            "$schema",
            "$defs",
            "title",
        ):
            schema.pop(key, None)

        if schema.get("type") == "string" and "format" in schema:
            if schema["format"] not in {"enum", "date-time"}:
                del schema["format"]

        for prop in (schema.get("properties") or {}).values():
            if isinstance(prop, dict):
                self._clean_schema_recursive(prop)

        if isinstance(schema.get("items"), dict):
            self._clean_schema_recursive(schema["items"])

        for key in ("anyOf", "allOf", "oneOf"):
            for item in schema.get(key) or []:
                if isinstance(item, dict):
                    self._clean_schema_recursive(item)

    # --- Response parsing ---

    def _parse_response(self, response, model: str) -> CompletionResponse:
        usage = self._parse_usage(response.usage_metadata)
        candidates = response.candidates
        if not candidates:
            return self._empty_response(model, usage)

        candidate = candidates[0]
        parts = candidate.content.parts if candidate.content else []
        content, tool_calls = self._parse_parts(parts)
        finish_reason = self._map_finish_reason(candidate.finish_reason)

        message = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls or None,
            reasoning_content=None,
        )

        return CompletionResponse(
            choices=[Choice(message=message, finish_reason=finish_reason)],
            usage=usage,
            model=model,
        )

    def _empty_response(self, model: str, usage: Usage) -> CompletionResponse:
        message = Message(role="assistant", content=None, tool_calls=None, reasoning_content=None)
        return CompletionResponse(
            choices=[Choice(message=message, finish_reason="stop")],
            usage=usage,
            model=model,
        )

    def _parse_parts(self, parts) -> tuple[str | None, list[ToolCall]]:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        call_seq = count()

        for part in parts:
            if part.text is not None:
                text_parts.append(part.text)
            elif part.function_call is not None:
                fc = part.function_call
                tool_calls.append(
                    ToolCall(
                        id=f"call_{fc.name}_{next(call_seq)}",
                        type="function",
                        function=FunctionCall(
                            name=fc.name,
                            arguments=json.dumps(dict(fc.args)) if fc.args else "{}",
                        ),
                    )
                )

        content = "\n".join(text_parts) if text_parts else None
        return content, tool_calls

    def _map_finish_reason(self, reason) -> str:
        mapping = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "FinishReason.STOP": "stop",
            "FinishReason.MAX_TOKENS": "length",
        }
        return mapping.get(str(reason) if reason else "STOP", "stop")

    def _parse_usage(self, usage_meta) -> Usage:
        if not usage_meta:
            return Usage(prompt_tokens=0, completion_tokens=0, cache_read_tokens=0, cache_write_tokens=0)
        total_prompt = usage_meta.prompt_token_count or 0
        cache_read = usage_meta.cached_content_token_count or 0
        return Usage(
            prompt_tokens=total_prompt - cache_read,
            completion_tokens=usage_meta.candidates_token_count or 0,
            cache_read_tokens=cache_read,
            cache_write_tokens=0,
        )
