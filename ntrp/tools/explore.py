from pydantic import BaseModel, Field

from ntrp.constants import EXPLORE_TIMEOUT
from ntrp.core.isolation import IsolationLevel
from ntrp.core.prompts import EXPLORE_PROMPT
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

EXPLORE_DESCRIPTION = (
    "Spawn an exploration agent for information gathering. "
    "Can run in parallel (call multiple in one turn) and nest recursively."
)


class ExploreInput(BaseModel):
    task: str = Field(description="What to explore or research.")


class ExploreTool(Tool):
    name = "explore"
    description = EXPLORE_DESCRIPTION
    input_model = ExploreInput

    async def _build_prompt(self, memory) -> str:
        if not memory:
            return EXPLORE_PROMPT

        user_facts, _ = await memory.get_context(user_limit=5, recent_limit=0)
        if not user_facts:
            return EXPLORE_PROMPT

        context = "\n".join(f"- {f.text}" for f in user_facts)
        return f"{EXPLORE_PROMPT}\n\nUSER CONTEXT:\n{context}"

    EXPLORE_TOOLS = {
        "notes",
        "read_note",
        "emails",
        "read_email",
        "calendar",
        "browser",
        "recall",
        "remember",
        "web_search",
        "web_fetch",
        "explore",
    }

    async def execute(self, execution: ToolExecution, task: str, **kwargs) -> ToolResult:
        ctx = execution.ctx

        if not ctx.spawn_fn:
            return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

        tools = ctx.registry.get_schemas(names=self.EXPLORE_TOOLS)
        prompt = await self._build_prompt(ctx.memory)

        result = await ctx.spawn_fn(
            ctx,
            task=task,
            system_prompt=prompt,
            tools=tools,
            timeout=EXPLORE_TIMEOUT,
            parent_id=execution.tool_id,
            isolation=IsolationLevel.FULL,
        )
        return ToolResult(content=result, preview="Explored")
