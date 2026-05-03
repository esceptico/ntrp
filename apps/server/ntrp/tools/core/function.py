from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict

from ntrp.agent import ToolResult
from ntrp.tools.core.base import Tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ApprovalInfo

ToolSet = dict[str, Tool]


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


ToolHandler = Callable[[ToolExecution, BaseModel], Awaitable[ToolResult]]
ApprovalHandler = Callable[[ToolExecution, BaseModel], Awaitable[ApprovalInfo | None]]


class _FunctionTool(Tool):
    """Tool adapter for plain Python callables."""

    def __init__(
        self,
        *,
        description: str,
        execute: ToolHandler,
        input_model: type[BaseModel] = EmptyInput,
        display_name: str | None = None,
        mutates: bool = False,
        volatile: bool = False,
        requires: Iterable[str] = (),
        approval: ApprovalHandler | None = None,
    ):
        self.display_name = display_name
        self.description = description
        self.input_model = input_model
        self.mutates = mutates
        self.volatile = volatile
        self.requires = frozenset(requires)
        self._execute = execute
        self._approval = approval

    async def approval_info(self, execution: ToolExecution, **kwargs: Any) -> ApprovalInfo | None:
        if self._approval is None:
            return None
        args = self.input_model(**kwargs)
        return await self._approval(execution, args)

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        args = self.input_model(**kwargs)
        result = await self._execute(execution, args)
        if not isinstance(result, ToolResult):
            raise TypeError("function tool handlers must return ToolResult")
        return result


def tool(
    *,
    description: str,
    execute: ToolHandler,
    input_model: type[BaseModel] = EmptyInput,
    display_name: str | None = None,
    mutates: bool = False,
    volatile: bool = False,
    requires: Iterable[str] = (),
    approval: ApprovalHandler | None = None,
) -> Tool:
    return _FunctionTool(
        description=description,
        execute=execute,
        input_model=input_model,
        display_name=display_name,
        mutates=mutates,
        volatile=volatile,
        requires=requires,
        approval=approval,
    )
