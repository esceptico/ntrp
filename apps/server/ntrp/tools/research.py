from pydantic import BaseModel, Field

from ntrp.agent.ledger import SharedLedger
from ntrp.constants import USER_ENTITY_NAME
from ntrp.core.isolation import IsolationLevel
from ntrp.core.prompts import RESEARCH_PROMPTS, current_date_formatted, env
from ntrp.logging import get_logger
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution

_logger = get_logger(__name__)


LEDGER_TEMPLATE = env.from_string("""\
RESEARCH CONTEXT (shared across all agents in this run):
{% if active %}Active:
{% for item in active %}- "{{ item.label }}" ({{ item.metadata.depth }})
{% endfor %}{% endif %}\
{% if done %}Done:
{% for item in done %}- "{{ item.label }}" ({{ item.metadata.depth }})
{% endfor %}{% endif %}\
{% if accessed %}Documents already read: {{ accessed }}
{% endif %}\
Do not re-research topics already covered. Focus on your specific scope.""")


def _format_ledger(ledger: SharedLedger, exclude_id: str | None = None) -> str:
    items = ledger.get_items(exclude_id=exclude_id)
    if not items and not ledger.accessed_count:
        return ""

    active = [item for item in items if not item.done]
    done = [item for item in items if item.done]
    return LEDGER_TEMPLATE.render(active=active, done=done, accessed=ledger.accessed_count)


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
    "Use depth='deep' for thorough research, 'quick' for fast lookups."
)


class ResearchInput(BaseModel):
    task: str = Field(description="What to research.")
    depth: str = Field(
        default="normal",
        description="How thorough: 'quick' (fast scan), 'normal' (balanced), 'deep' (exhaustive).",
    )


async def _build_research_prompt(ctx, depth: str, remaining_depth: int, tool_id: str) -> str:
    ledger_summary = None
    if ctx.ledger:
        ledger_summary = _format_ledger(ctx.ledger, exclude_id=tool_id)

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


async def research(execution: ToolExecution, args: ResearchInput) -> ToolResult:
    ctx = execution.ctx

    if not ctx.spawn_fn:
        return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

    if ctx.ledger:
        await ctx.ledger.register(execution.tool_id, args.task, depth=args.depth)

    remaining = ctx.run.max_depth - ctx.run.current_depth - 1
    exclude = {"background", "cancel_background_task", "list_background_tasks", "get_background_result"}
    if args.depth == "quick" or remaining <= 1:
        exclude.add("research")

    tools = ctx.registry.get_schemas(mutates=False, capabilities=ctx.capabilities)
    tools = [t for t in tools if t["function"]["name"] not in exclude]
    prompt = await _build_research_prompt(ctx, args.depth, remaining, execution.tool_id)
    try:
        result = await ctx.spawn_fn(
            ctx,
            task=args.task,
            system_prompt=prompt,
            tools=tools,
            model_override=ctx.run.research_model,
            parent_id=execution.tool_id,
            isolation=IsolationLevel.FULL,
        )
    finally:
        if ctx.ledger:
            await ctx.ledger.complete(execution.tool_id)

    return ToolResult(content=result, preview=f"Researched ({args.depth})")


research_tool = tool(
    display_name="Research",
    description=RESEARCH_DESCRIPTION,
    input_model=ResearchInput,
    execute=research,
)
