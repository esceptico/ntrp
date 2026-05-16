import asyncio
from collections.abc import AsyncGenerator

from ntrp.agent.tools.runner import ToolRunner
from ntrp.agent.types.events import ToolCompleted, ToolStarted
from ntrp.agent.types.llm import Role
from ntrp.agent.types.tool_call import PendingToolCall, ToolCall


async def dispatch_tools(
    runner: ToolRunner,
    messages: list[dict],
    calls: list[PendingToolCall],
    raw_tool_calls: list[ToolCall],
) -> AsyncGenerator[ToolStarted | ToolCompleted]:
    results: dict[str, str] = {}

    try:
        async for event in runner.execute_all(calls):
            if isinstance(event, ToolCompleted):
                results[event.tool_id] = event.result
            yield event
    except asyncio.CancelledError:
        _append_results(messages, raw_tool_calls, results, missing_content="Tool call cancelled.")
        raise

    _append_results(messages, raw_tool_calls, results, missing_content="Tool call result missing.")


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
