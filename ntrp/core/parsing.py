import json
from typing import Any

from ntrp.core.models import PendingToolCall


def parse_tool_arguments(arguments: str | None) -> dict:
    if not arguments:
        return {}
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return {}


def sanitize_assistant_message(message: Any) -> dict:
    sanitized: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    if message.tool_calls:
        sanitized["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    # Preserve reasoning_content for models with thinking enabled (e.g. Kimi K2.5)
    if hasattr(message, "reasoning_content") and message.reasoning_content:
        sanitized["reasoning_content"] = message.reasoning_content
    return sanitized


def parse_tool_calls(tool_calls: list[Any]) -> list[PendingToolCall]:
    return [
        PendingToolCall(
            tool_call=tc,
            name=tc.function.name,
            args=parse_tool_arguments(tc.function.arguments),
        )
        for tc in tool_calls
    ]
