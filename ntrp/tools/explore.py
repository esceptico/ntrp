from typing import Literal

from pydantic import BaseModel, Field

from ntrp.constants import EXPLORE_TIMEOUT, USER_ENTITY_NAME
from ntrp.core.isolation import IsolationLevel
from ntrp.core.prompts import EXPLORE_PROMPTS, current_date_formatted, env
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

EXPLORE_SYSTEM_PROMPT = env.from_string("""{{ base_prompt }}

Today is {{ date }}.
{% if remaining_depth > 1 %}

DEPTH BUDGET: You can spawn {{ remaining_depth - 1 }} more levels of sub-agents. Use explore() to delegate sub-topics — don't try to cover everything yourself.
{% elif remaining_depth == 1 %}

DEPTH BUDGET: You are at the last level — no more sub-agents. Do all work directly.
{% endif %}
{% if ledger_summary %}

{{ ledger_summary }}
{% endif %}
{% if user_facts %}

USER CONTEXT:
{% for fact in user_facts -%}
- {{ fact.text }}
{% endfor %}
{% endif %}""")

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

    async def _build_prompt(self, ctx, depth: str, remaining_depth: int, tool_id: str) -> str:
        ledger_summary = None
        if ctx.ledger:
            ledger_summary = await ctx.ledger.summary(exclude_id=tool_id)

        user_facts = []
        memory = ctx.services.get("memory")
        if memory:
            user_facts = await memory.facts.get_facts_for_entity(USER_ENTITY_NAME, limit=5)

        return EXPLORE_SYSTEM_PROMPT.render(
            base_prompt=EXPLORE_PROMPTS[depth],
            date=current_date_formatted(),
            remaining_depth=remaining_depth,
            ledger_summary=ledger_summary,
            user_facts=user_facts,
        )

    async def execute(self, execution: ToolExecution, task: str, depth: str = "normal", **kwargs) -> ToolResult:
        ctx = execution.ctx

        if not ctx.spawn_fn:
            return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

        if ctx.ledger:
            await ctx.ledger.register(execution.tool_id, task, depth)

        remaining = ctx.run.max_depth - ctx.run.current_depth - 1
        exclude = {"explore"} if depth == "quick" or remaining <= 1 else None

        tools = ctx.registry.get_schemas(mutates=False, capabilities=ctx.capabilities)
        if exclude:
            tools = [t for t in tools if t["name"] not in exclude]
        prompt = await self._build_prompt(ctx, depth, remaining, execution.tool_id)
        timeout = DEPTH_TIMEOUTS[depth]

        try:
            result = await ctx.spawn_fn(
                ctx,
                task=task,
                system_prompt=prompt,
                tools=tools,
                timeout=timeout,
                model_override=ctx.run.explore_model,
                parent_id=execution.tool_id,
                isolation=IsolationLevel.FULL,
            )
        finally:
            if ctx.ledger:
                await ctx.ledger.complete(execution.tool_id)

        return ToolResult(content=result, preview=f"Explored ({depth})")
