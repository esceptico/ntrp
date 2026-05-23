from dataclasses import replace

from ntrp.agent.model_request import ModelRequest, ModelRequestNext
from ntrp.agent.types.llm import Role
from ntrp.constants import OFFLOAD_PREVIEW_CHARS

HISTORY_TOOL_RESULT_PREVIEW_CHARS = OFFLOAD_PREVIEW_CHARS
MODEL_TOOL_RESULT_PREVIEW_CHARS = 2_500
MODEL_TOOL_RESULT_TOTAL_PREVIEW_CHARS = 18_000
MODEL_TOOL_RESULT_EXHAUSTED_PREVIEW_CHARS = 160


class ToolResultContextBudgetMiddleware:
    async def __call__(self, request: ModelRequest, next_request: ModelRequestNext) -> ModelRequest:
        prepared = await next_request(request)
        messages = clamp_tool_results_for_model_context(prepared.messages)
        if messages is prepared.messages:
            return prepared
        return replace(prepared, messages=messages)


def clamp_tool_results_for_model_context(messages: list[dict]) -> list[dict]:
    changed = False
    clamped: list[dict] = []
    remaining_tool_preview = MODEL_TOOL_RESULT_TOTAL_PREVIEW_CHARS
    for message in messages:
        next_message, used = _clamp_tool_message(message, remaining_tool_preview)
        remaining_tool_preview -= used
        changed = changed or next_message is not message
        clamped.append(next_message)
    return clamped if changed else messages


def _clamp_tool_message(message: dict, remaining_tool_preview: int) -> tuple[dict, int]:
    if message.get("role") not in {Role.TOOL, "tool"}:
        return message, 0
    content = message.get("content")
    if not isinstance(content, str) or len(content) <= MODEL_TOOL_RESULT_PREVIEW_CHARS:
        return message, len(content) if isinstance(content, str) else 0

    if remaining_tool_preview <= 0:
        limit = MODEL_TOOL_RESULT_EXHAUSTED_PREVIEW_CHARS
    else:
        limit = min(MODEL_TOOL_RESULT_PREVIEW_CHARS, remaining_tool_preview)
    compact = compact_tool_result_text(content, surface="model context", limit=limit)
    return {**message, "content": compact}, len(compact)


def compact_tool_result_text(
    content: str,
    *,
    surface: str,
    limit: int = MODEL_TOOL_RESULT_PREVIEW_CHARS,
) -> str:
    footer = f"\n... [{surface} preview truncated]"
    header = (
        f"[Tool result compacted for {surface}: "
        f"{len(content)} chars total, showing preview only. "
        "Full result remains in the transcript/tool result store; use a narrower search/read if needed.]\n"
    )
    if limit <= len(header) + len(footer):
        brief = f"[Tool result compacted for {surface}: {len(content)} chars total. Preview omitted.]"
        if len(brief) <= limit:
            return brief
        return f"{brief[: max(0, limit - 3)]}..."

    preview_budget = limit - len(header) - len(footer)
    return f"{header}{content[:preview_budget]}{footer}"
