from typing import Literal

from pydantic import BaseModel, Field

from ntrp.agent.coverage import ResearchOutline
from ntrp.agent.ledger import ContradictionNote, DeadEndNote, FactNote, GapNote, SharedLedger
from ntrp.core.isolation import IsolationLevel
from ntrp.core.prompts import RESEARCH_PROMPTS, current_date_formatted, env
from ntrp.logging import get_logger
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolContext, ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope
from ntrp.tools.research_artifacts import (
    append_research_artifact_tool,
    list_research_artifacts_tool,
    read_research_artifact_tool,
    write_research_artifact_tool,
)

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
{% if notes %}Research notes:
{% for note in notes %}- {{ note }}
{% endfor %}{% endif %}\
{% if coverage %}Coverage: {{ coverage.coverage }}%; gaps: {{ coverage.gaps | join(", ") if coverage.gaps else "none" }}
{% endif %}\
Do not re-research topics already covered. Focus on your specific scope.""")


def _format_ledger(
    ledger: SharedLedger,
    exclude_id: str | None = None,
    *,
    coverage_scope: str = "default",
) -> str:
    items = ledger.get_items(exclude_id=exclude_id)
    notes = [_format_note(note) for note in ledger.notes[-12:]]
    coverage_report = ledger.coverage_report(scope=coverage_scope)
    coverage = (
        {
            "coverage": round(coverage_report.coverage * 100),
            "gaps": coverage_report.gaps,
        }
        if coverage_report is not None
        else None
    )
    if not items and not ledger.accessed_count and not notes and coverage is None:
        return ""

    active = [item for item in items if not item.done]
    done = [item for item in items if item.done]
    return LEDGER_TEMPLATE.render(active=active, done=done, accessed=ledger.accessed_count, notes=notes, coverage=coverage)


def _format_note(note) -> str:
    if isinstance(note, FactNote):
        quote = f' quote="{note.quote}"' if note.quote else ""
        return f"fact: {note.claim} (source: {note.source}{quote})"
    if isinstance(note, DeadEndNote):
        return f"dead_end: tried {note.tried}; failed because {note.why_failed}"
    if isinstance(note, ContradictionNote):
        return f"contradiction: {note.claim_a} ({note.source_a}) vs {note.claim_b} ({note.source_b})"
    if isinstance(note, GapNote):
        return f"gap: {note.what_missing}"
    return str(note)


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
{% if memory_context %}

USER CONTEXT:
{{ memory_context }}
{% endif %}
{% if activated_skill_context %}

{{ activated_skill_context }}
{% endif %}

RESEARCH LEDGER TOOLS — record AS YOU GO, never batched at the end:
- The ledger is shared LIVE with the other research agents in this run. The moment you learn something, call research_note() to record facts, dead ends, contradictions, and gaps; the moment a source supports an outline section, call research_cover(). For deep or broad tasks, call research_outline() early with the sections the answer must cover.
- Record after each source you read, before moving to the next. Batching all notes at the end defeats the ledger — parallel agents can't see your progress and re-do the same analysis.
- Do not hide unsupported claims. If a claim is weak, contradictory, or missing evidence, record it as a note and say so in the final answer.

SCRATCHPAD (for long output):
- For bulky intermediates — long source inventories, large tables, draft reports — write them to an artifact with write_research_artifact()/append_research_artifact() instead of carrying everything in context, and read_research_artifact() back specific parts as needed.
- Keep your final answer a concise, distilled summary; the caller automatically sees the artifact manifest.""")

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


class ResearchNoteInput(BaseModel):
    kind: Literal["fact", "dead_end", "contradiction", "gap"] = Field(description="Type of note to record.")
    claim: str | None = Field(default=None, description="Fact claim. Required for kind='fact'.")
    source: str | None = Field(default=None, description="Source path, URL, message id, or tool result reference.")
    quote: str | None = Field(default=None, description="Short supporting quote for kind='fact'.")
    tried: str | None = Field(default=None, description="Attempted query/source/path. Required for kind='dead_end'.")
    why_failed: str | None = Field(default=None, description="Failure reason. Required for kind='dead_end'.")
    claim_a: str | None = Field(default=None, description="First conflicting claim.")
    source_a: str | None = Field(default=None, description="Source for first conflicting claim.")
    claim_b: str | None = Field(default=None, description="Second conflicting claim.")
    source_b: str | None = Field(default=None, description="Source for second conflicting claim.")
    what_missing: str | None = Field(default=None, description="Missing information. Required for kind='gap'.")


class ResearchOutlineInput(BaseModel):
    sections: list[str] = Field(description="Required coverage sections for this research task.")


class ResearchCoverInput(BaseModel):
    section: str = Field(description="Outline section title covered by the source.")
    source: str = Field(description="Source path, URL, message id, or tool result reference.")


async def _build_research_prompt(ctx, depth: str, remaining_depth: int, tool_id: str) -> str:
    ledger_summary = None
    if ctx.ledger:
        ledger_summary = _format_ledger(
            ctx.ledger,
            exclude_id=tool_id,
            coverage_scope=ctx.run.research_scope_id or "default",
        )

    return RESEARCH_SYSTEM_PROMPT.render(
        base_prompt=RESEARCH_PROMPTS[depth],
        date=current_date_formatted(),
        remaining_depth=remaining_depth,
        ledger_summary=ledger_summary,
        memory_context=None,
        activated_skill_context=None,
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

    tools = ctx.registry.get_schemas(read_only=True, capabilities=ctx.capabilities)
    tools = [t for t in tools if t["function"]["name"] not in exclude and t["function"]["name"] not in RESEARCH_AGENT_TOOLS]
    missing_research_agent_tools = {
        name: agent_tool
        for name, agent_tool in RESEARCH_AGENT_TOOLS.items()
        if name not in ctx.registry
    }
    tools.extend(agent_tool.to_dict(name) for name, agent_tool in RESEARCH_AGENT_TOOLS.items())
    prompt = await _build_research_prompt(ctx, args.depth, remaining, execution.tool_id)
    try:
        spawn = await ctx.spawn_fn(
            ctx,
            task=args.task,
            system_prompt=prompt,
            tools=tools,
            model_override=ctx.run.research_model,
            parent_id=execution.tool_id,
            isolation=IsolationLevel.FULL,
            kind="research",
            extra_tools=missing_research_agent_tools,
            compaction_prompt_context="research",
            include_tool_messages_in_compaction=True,
            research_scope_id=execution.tool_id,
        )
    finally:
        if ctx.ledger:
            await ctx.ledger.complete(execution.tool_id)

    # Carry the subagent's own usage + cost out via `data` so the desktop
    # can render a per-agent budget breakdown on its trace row. The cost
    # has already rolled into the caller's tracker inside spawn_fn.
    data: dict = {}
    if spawn.usage is not None:
        data["usage"] = spawn.usage
        data["cost"] = spawn.cost
    if artifacts := await _list_scope_artifacts(ctx, execution.tool_id):
        data["artifacts"] = artifacts
    return ToolResult(content=spawn.text, preview=f"Researched ({args.depth})", data=data or None)


async def _list_scope_artifacts(ctx: ToolContext, scope_id: str) -> list[dict]:
    store = ctx.services.get("store")
    if store is None:
        svc = ctx.services.get("session")
        store = getattr(svc, "store", None) if svc else None
    if store is None:
        return []
    rows = await store.list_research_artifacts(scope_id=scope_id)
    return [{"path": r["path"], "bytes": r["byte_len"], "preview": r["preview"]} for r in rows]


async def research_note(execution: ToolExecution, args: ResearchNoteInput) -> ToolResult:
    ledger = execution.ctx.ledger
    if not ledger:
        return ToolResult(content="Error: research ledger not available", preview="No ledger", is_error=True)

    if args.kind == "fact":
        if not args.claim or not args.source:
            return ToolResult(content="fact notes require claim and source", preview="Invalid note", is_error=True)
        note = FactNote(claim=args.claim, source=args.source, quote=args.quote)
    elif args.kind == "dead_end":
        if not args.tried or not args.why_failed:
            return ToolResult(content="dead_end notes require tried and why_failed", preview="Invalid note", is_error=True)
        note = DeadEndNote(tried=args.tried, why_failed=args.why_failed)
    elif args.kind == "contradiction":
        if not args.claim_a or not args.source_a or not args.claim_b or not args.source_b:
            return ToolResult(
                content="contradiction notes require claim_a, source_a, claim_b, and source_b",
                preview="Invalid note",
                is_error=True,
            )
        note = ContradictionNote(
            claim_a=args.claim_a,
            source_a=args.source_a,
            claim_b=args.claim_b,
            source_b=args.source_b,
        )
    else:
        if not args.what_missing:
            return ToolResult(content="gap notes require what_missing", preview="Invalid note", is_error=True)
        note = GapNote(what_missing=args.what_missing)

    ledger.add_note(note)
    return ToolResult(content=f"Recorded research note: {_format_note(note)}", preview=f"Recorded {args.kind}")


async def research_outline(execution: ToolExecution, args: ResearchOutlineInput) -> ToolResult:
    ledger = execution.ctx.ledger
    if not ledger:
        return ToolResult(content="Error: research ledger not available", preview="No ledger", is_error=True)
    sections = [section.strip() for section in args.sections if section.strip()]
    try:
        outline = ResearchOutline.from_titles(sections)
    except ValueError as exc:
        return ToolResult(content=str(exc), preview="Invalid outline", is_error=True)
    ledger.set_outline(outline, scope=execution.ctx.run.research_scope_id or "default")
    return ToolResult(content=f"Research outline set: {', '.join(outline.titles)}", preview=f"Outline {len(outline.titles)} sections")


async def research_cover(execution: ToolExecution, args: ResearchCoverInput) -> ToolResult:
    ledger = execution.ctx.ledger
    if not ledger:
        return ToolResult(content="Error: research ledger not available", preview="No ledger", is_error=True)
    try:
        ledger.cover_section(args.section, args.source, scope=execution.ctx.run.research_scope_id or "default")
    except ValueError as exc:
        return ToolResult(content=str(exc), preview="Coverage failed", is_error=True)
    report = ledger.coverage_report(scope=execution.ctx.run.research_scope_id or "default")
    assert report is not None
    percent = round(report.coverage * 100)
    gaps = ", ".join(report.gaps) if report.gaps else "none"
    return ToolResult(
        content=f"Covered {args.section} with {args.source}. Coverage: {percent}%; gaps: {gaps}",
        preview=f"Coverage {percent}%",
    )


research_tool = tool(
    display_name="Research",
    description=RESEARCH_DESCRIPTION,
    input_model=ResearchInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=research,
    kind="agent",
)

research_note_tool = tool(
    display_name="Research Note",
    description="Record a source-backed research fact, dead end, contradiction, or gap in the shared run ledger.",
    input_model=ResearchNoteInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, offload=False),
    execute=research_note,
)

research_outline_tool = tool(
    display_name="Research Outline",
    description="Set the required coverage sections for a broad or deep research task.",
    input_model=ResearchOutlineInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, offload=False),
    execute=research_outline,
)

research_cover_tool = tool(
    display_name="Research Cover",
    description="Mark an outline section as covered by a specific source.",
    input_model=ResearchCoverInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, offload=False),
    execute=research_cover,
)

RESEARCH_AGENT_TOOLS = {
    "research_note": research_note_tool,
    "research_outline": research_outline_tool,
    "research_cover": research_cover_tool,
    "write_research_artifact": write_research_artifact_tool,
    "append_research_artifact": append_research_artifact_tool,
    "read_research_artifact": read_research_artifact_tool,
    "list_research_artifacts": list_research_artifacts_tool,
}
