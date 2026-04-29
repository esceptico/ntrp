from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


@dataclass(frozen=True)
class ToolCall:
    name: str
    tool: Tool
    execution: ToolExecution
    arguments: dict[str, Any]


ToolNext = Callable[[ToolCall], Awaitable[ToolResult]]
ToolMiddleware = Callable[[ToolCall, ToolNext], Awaitable[ToolResult]]


async def validate_arguments(call: ToolCall, next_call: ToolNext) -> ToolResult:
    if call.tool.input_model is None:
        return await next_call(call)

    try:
        validated = call.tool.input_model(**call.arguments)
    except ValidationError as e:
        errors = "; ".join(
            f"{'.'.join(str(l) for l in err['loc'])}: {err['msg']}" for err in e.errors() if err.get("loc")
        )
        return ToolResult(
            content=f"Invalid arguments: {errors}",
            preview="Validation error",
            is_error=True,
        )

    return await next_call(replace(call, arguments=validated.model_dump()))


async def request_approval(call: ToolCall, next_call: ToolNext) -> ToolResult:
    info = await call.tool.approval_info(call.execution, **call.arguments)
    if info is None:
        return await next_call(call)

    rejection = await call.execution.request_approval(
        info.description,
        preview=info.preview,
        diff=info.diff,
    )
    if rejection is not None:
        return rejection.to_result()

    return await next_call(call)


DEFAULT_TOOL_MIDDLEWARE: tuple[ToolMiddleware, ...] = (validate_arguments, request_approval)
