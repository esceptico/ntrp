import base64
import json
from typing import Any

from ntrp.core.models import PendingToolCall
from ntrp.logging import get_logger

_logger = get_logger(__name__)


def parse_tool_arguments(arguments: str | None) -> dict:
    if not arguments:
        return {}
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        _logger.warning("Malformed tool arguments: %.200s", arguments)
        return {}


def normalize_assistant_message(message: Any) -> dict:
    """Normalize LLM response into a serializable message dict."""
    sanitized: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    if message.tool_calls:
        tool_calls = []
        for tc in message.tool_calls:
            tc_dict = {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            if tc.thought_signature:
                tc_dict["thought_signature"] = base64.b64encode(tc.thought_signature).decode()
            tool_calls.append(tc_dict)
        sanitized["tool_calls"] = tool_calls
    if message.reasoning_content:
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
