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
    display_name = "Explore"
    description = EXPLORE_DESCRIPTION
    input_model = ExploreInput

    async def _build_prompt(self, memory, depth: str, remaining_depth: int) -> str:
        base = EXPLORE_PROMPTS[depth]

        parts = [base]

        if remaining_depth > 1:
            parts.append(
                f"DEPTH BUDGET: You can spawn {remaining_depth - 1} more levels of sub-agents. "
                "Use explore() to delegate sub-topics — don't try to cover everything yourself."
            )
        elif remaining_depth == 1:
            parts.append("DEPTH BUDGET: You are at the last level — no more sub-agents. Do all work directly.")

        if memory:
            user_facts, _ = await memory.get_context(user_limit=5, recent_limit=0)
            if user_facts:
                context = "\n".join(f"- {f.text}" for f in user_facts)
                parts.append(f"USER CONTEXT:\n{context}")

        return "\n\n".join(parts)

    EXPLORE_TOOLS = {
        "notes",
        "read_note",
        "emails",
        "read_email",
        "calendar",
        "browser",
        "recall",
        "web_search",
        "web_fetch",
        "explore",
    }

    async def execute(self, execution: ToolExecution, task: str, depth: str = "normal", **kwargs) -> ToolResult:
        ctx = execution.ctx

        if not ctx.spawn_fn:
            return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

        remaining = ctx.max_depth - ctx.current_depth - 1
        tool_names = set(self.EXPLORE_TOOLS)
        if depth == "quick" or remaining <= 1:
            tool_names.discard("explore")

        tools = ctx.registry.get_schemas(names=tool_names)
        prompt = await self._build_prompt(ctx.memory, depth, remaining)
        timeout = DEPTH_TIMEOUTS[depth]

        result = await ctx.spawn_fn(
            ctx,
            task=task,
            system_prompt=prompt,
            tools=tools,
            timeout=timeout,
            model_override=ctx.explore_model,
            parent_id=execution.tool_id,
            isolation=IsolationLevel.FULL,
        )
        return ToolResult(content=result, preview=f"Explored ({depth})")
