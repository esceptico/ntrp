from typing import Protocol

from ntrp.agent.types.tools import ToolMeta, ToolResult


class AgentToolExecutor(Protocol):
    async def execute(self, name: str, args: dict) -> ToolResult: ...

    def get_meta(self, name: str) -> ToolMeta | None: ...
