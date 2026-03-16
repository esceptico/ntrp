import asyncio
import time

from pydantic import BaseModel, Field

from ntrp.constants import RESEARCH_TIMEOUT, USER_ENTITY_NAME
from ntrp.core.isolation import IsolationLevel
from ntrp.core.prompts import RESEARCH_PROMPTS, current_date_formatted, env
from ntrp.events.sse import BackgroundTaskEvent
from ntrp.logging import get_logger
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

_logger = get_logger(__name__)

RESEARCH_SYSTEM_PROMPT = env.from_string("""{{ base_prompt }}

Today is {{ date }}.
{% if remaining_depth > 1 %}

DEPTH BUDGET: You can spawn {{ remaining_depth - 1 }} more levels of sub-agents. Use research() to delegate sub-topics — don't try to cover everything yourself.
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

RESEARCH_DESCRIPTION = (
    "Spawn a research agent with access to all read-only tools. "
    "Can run in parallel (call multiple in one turn) and nest recursively. "
    "Use depth='deep' for thorough research, 'quick' for fast lookups. "
    "Set background=true to run without blocking — results are delivered automatically."
)

DEPTH_TIMEOUTS = {
    "quick": 120,
    "normal": RESEARCH_TIMEOUT,
    "deep": 600,
}


class ResearchInput(BaseModel):
    task: str = Field(description="What to research.")
    depth: str = Field(
        default="normal",
        description="How thorough: 'quick' (fast scan), 'normal' (balanced), 'deep' (exhaustive).",
    )
    background: bool = Field(
        default=False,
        description="Run in background, return immediately. Results delivered automatically when done.",
    )


class ResearchTool(Tool):
    name = "research"
    display_name = "Research"
    description = RESEARCH_DESCRIPTION
    input_model = ResearchInput

    async def _build_prompt(self, ctx, depth: str, remaining_depth: int, tool_id: str) -> str:
        ledger_summary = None
        if ctx.ledger:
            ledger_summary = await ctx.ledger.summary(exclude_id=tool_id)

        user_facts = []
        memory = ctx.services.get("memory")
        if memory:
            user_facts = await memory.facts.get_facts_for_entity(USER_ENTITY_NAME, limit=5)

        return RESEARCH_SYSTEM_PROMPT.render(
            base_prompt=RESEARCH_PROMPTS[depth],
            date=current_date_formatted(),
            remaining_depth=remaining_depth,
            ledger_summary=ledger_summary,
            user_facts=user_facts,
        )

    async def execute(
        self, execution: ToolExecution, task: str, depth: str = "normal", background: bool = False, **kwargs
    ) -> ToolResult:
        ctx = execution.ctx

        if not ctx.spawn_fn:
            return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

        if ctx.ledger:
            await ctx.ledger.register(execution.tool_id, task, depth)

        remaining = ctx.run.max_depth - ctx.run.current_depth - 1
        exclude = {"research"} if depth == "quick" or remaining <= 1 else None

        tools = ctx.registry.get_schemas(mutates=False, capabilities=ctx.capabilities)
        if exclude:
            tools = [t for t in tools if t["function"]["name"] not in exclude]
        prompt = await self._build_prompt(ctx, depth, remaining, execution.tool_id)
        timeout = DEPTH_TIMEOUTS[depth]

        if not background:
            try:
                result = await ctx.spawn_fn(
                    ctx,
                    task=task,
                    system_prompt=prompt,
                    tools=tools,
                    timeout=timeout,
                    model_override=ctx.run.research_model,
                    parent_id=execution.tool_id,
                    isolation=IsolationLevel.FULL,
                )
            finally:
                if ctx.ledger:
                    await ctx.ledger.complete(execution.tool_id)

            return ToolResult(content=result, preview=f"Researched ({depth})")

        registry = ctx.background_tasks
        bg_task_id = registry.generate_id()
        label = f"research({depth}): {task}"

        async def _run_background():
            start = time.monotonic()
            try:
                result = await ctx.spawn_fn(
                    ctx,
                    task=task,
                    system_prompt=prompt,
                    tools=tools,
                    timeout=timeout,
                    model_override=ctx.run.research_model,
                    parent_id=execution.tool_id,
                    isolation=IsolationLevel.FULL,
                    silent=True,
                )
                status = "completed"
            except asyncio.CancelledError:
                if ctx.ledger:
                    await ctx.ledger.complete(execution.tool_id)
                return
            except Exception as e:
                result = f"Error: {e}"
                status = "failed"
                _logger.warning("Background research %s failed: %s", bg_task_id, e)
            duration_ms = int((time.monotonic() - start) * 1000)
            if ctx.ledger:
                await ctx.ledger.complete(execution.tool_id)

            await registry.deliver_result(
                task_id=bg_task_id,
                result=result,
                label=label,
                status=status,
                duration_ms=duration_ms,
                tool_name="research",
                tool_args={"task": task, "depth": depth},
                display_name="Research",
                emit=ctx.io.emit,
            )

        async_task = asyncio.create_task(_run_background())
        registry.register(bg_task_id, async_task, command=label)

        if ctx.io.emit:
            await ctx.io.emit(BackgroundTaskEvent(task_id=bg_task_id, command=label, status="started"))

        return ToolResult(
            content=f"Background research {bg_task_id} started: {task}",
            preview=f"Background · {bg_task_id}",
        )
