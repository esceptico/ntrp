import asyncio
from collections.abc import AsyncGenerator

from ntrp.agent.tools.runner import ToolRunner
from ntrp.agent.types.events import ToolCompleted, ToolStarted
from ntrp.agent.types.llm import Role
from ntrp.agent.types.tool_call import PendingToolCall, ToolCall
from ntrp.core.content import ContentBlock, ContextContent


async def dispatch_tools(
    runner: ToolRunner,
    messages: list[dict],
    calls: list[PendingToolCall],
    raw_tool_calls: list[ToolCall],
) -> AsyncGenerator[ToolStarted | ToolCompleted]:
    results: dict[str, str] = {}
    model_content: dict[str, tuple[ContentBlock, ...]] = {}

    try:
        async for event in runner.execute_all(calls):
            if isinstance(event, ToolCompleted):
                results[event.tool_id] = event.result
                if event.model_content:
                    model_content[event.tool_id] = event.model_content
            yield event
    except asyncio.CancelledError:
        _append_results(messages, raw_tool_calls, results, missing_content="Tool call cancelled.")
        _append_model_content(messages, raw_tool_calls, model_content)
        raise

    _append_results(messages, raw_tool_calls, results, missing_content="Tool call result missing.")
    _append_model_content(messages, raw_tool_calls, model_content)


def _append_results(
    messages: list[dict],
    tool_calls: list[ToolCall],
    results: dict[str, str],
    *,
    missing_content: str,
) -> None:
    for tc in tool_calls:
        messages.append(
            {
                "role": Role.TOOL,
                "tool_call_id": tc.id,
                "content": results.get(tc.id, missing_content),
            }
        )


def _append_model_content(
    messages: list[dict],
    tool_calls: list[ToolCall],
    model_content: dict[str, tuple[ContentBlock, ...]],
) -> None:
    for tc in tool_calls:
        blocks = model_content.get(tc.id)
        if not blocks:
            continue
        messages.append(
            {
                "role": Role.USER,
                "client_id": f"tool-media:{tc.id}",
                "is_meta": True,
                "content": [
                    _content_block_dict(
                        ContextContent(
                            content_type="tool_result_media",
                            content=f"Media returned by tool {tc.function.name}.",
                            metadata={"tool_call_id": tc.id, "tool_name": tc.function.name},
                        )
                    ),
                    *(_content_block_dict(block) for block in blocks),
                ],
            }
        )


def _content_block_dict(block: ContentBlock) -> dict:
    return block.model_dump() if hasattr(block, "model_dump") else dict(block)
