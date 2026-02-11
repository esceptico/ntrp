from typing import Literal

from pydantic import BaseModel, Field

from ntrp.constants import EXPLORE_TIMEOUT
from ntrp.core.isolation import IsolationLevel
from ntrp.core.prompts import EXPLORE_PROMPTS
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

EXPLORE_DESCRIPTION = (
    "Spawn an exploration agent for information gathering. "
    "Can run in parallel (call multiple in one turn) and nest recursively. "
    "Use depth='deep' for thorough research, 'quick' for fast lookups."
)

DEPTH_TIMEOUTS = {
    "quick": 120,
    "normal": EXPLORE_TIMEOUT,
    "deep": 600,
}


class ExploreInput(BaseModel):
    task: str = Field(description="What to explore or research.")
    depth: Literal["quick", "normal", "deep"] = Field(
        default="normal",
        description="How thorough: 'quick' (fast scan), 'normal' (balanced), 'deep' (exhaustive).",
    )


class ExploreTool(Tool):
    name = "explore"
    description = EXPLORE_DESCRIPTION
    input_model = ExploreInput

    async def _build_prompt(self, memory, depth: str) -> str:
        base = EXPLORE_PROMPTS[depth]
        if not memory:
            return base

        user_facts, _ = await memory.get_context(user_limit=5, recent_limit=0)
        if not user_facts:
            return base

        context = "\n".join(f"- {f.text}" for f in user_facts)
        return f"{base}\n\nUSER CONTEXT:\n{context}"

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

    async def execute(self, execution: ToolExecution, task: str, depth: str = "normal", **kwargs) -> ToolResult:
        ctx = execution.ctx

        if not ctx.spawn_fn:
            return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

        tools = ctx.registry.get_schemas(names=self.EXPLORE_TOOLS)
        prompt = await self._build_prompt(ctx.memory, depth)
        timeout = DEPTH_TIMEOUTS[depth]

        result = await ctx.spawn_fn(
            ctx,
            task=task,
            system_prompt=prompt,
            tools=tools,
            timeout=timeout,
            parent_id=execution.tool_id,
            isolation=IsolationLevel.FULL,
        )
        return ToolResult(content=result, preview=f"Explored ({depth})")
