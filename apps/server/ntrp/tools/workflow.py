import asyncio
import json
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ntrp.events.sse import WorkflowFinishedEvent, WorkflowStartedEvent
from ntrp.orchestra.dynamic import format_script_traceback, run_script
from ntrp.orchestra.engine import Orchestra
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope


class WorkflowInput(BaseModel):
    script: str | None = Field(
        default=None,
        description="Python orchestration script (inline). Uses await agent()/parallel()/pipeline(), "
        "phase(), log(), `args`, `json`, and `return`s a result. Omit when running a saved preset by `name`.",
    )
    name: str | None = Field(
        default=None,
        description="Name of a saved workflow preset to run (e.g. 'audit'). Pass its parameters via `args`. "
        "Omit when passing an inline `script`. Use one of `script` or `name`, not both.",
    )
    title: str | None = Field(
        default=None,
        description="Short label for this run, shown in the UI. Defaults to the preset name when running by `name`.",
    )
    phases: list[str] = Field(
        default_factory=list,
        description="The plan: your script's phase titles in order (2-4), EXACTLY matching its phase() calls. "
        "The UI renders them as pending segments before any agent spawns. "
        "Declare these with an inline `script`; omit when running a preset by `name` (presets title their own phases).",
    )
    args: dict = Field(default_factory=dict, description="Values exposed to the script as `args`.")


class SaveWorkflowInput(BaseModel):
    name: str = Field(description="Preset name: lowercase letters/digits/hyphens, starts with a letter (e.g. 'memory-audit').")
    description: str = Field(description="One line — when to use this preset and what `args` it expects.")
    script: str = Field(description="The full Python workflow script to save (the same script you'd pass to `workflow`).")


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _render(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(_jsonable(result), indent=2, default=str)
    except (TypeError, ValueError):
        return str(result)


async def run_workflow(execution: ToolExecution, args: WorkflowInput) -> ToolResult:
    ctx = execution.ctx
    if ctx.spawn_fn is None:
        return ToolResult(content="Error: spawn capability not available", preview="No spawn", is_error=True)

    # Resolve the script: an inline `script`, or a saved preset by `name`.
    script = args.script
    description = None
    if args.name:
        if script:
            return ToolResult(
                content="Pass either `script` (inline) or `name` (a saved preset), not both.",
                preview="Conflicting inputs",
                is_error=True,
            )
        registry = ctx.services.get("skill_registry")
        if registry is None:
            return ToolResult(content="Error: skill registry not available.", preview="Unavailable", is_error=True)
        script = registry.load_workflow_script(args.name)
        if script is not None:
            description = registry.get(args.name).description
        else:
            presets = ", ".join(m.name for m in registry.list_all() if m.kind == "workflow")
            return ToolResult(
                content=f"No workflow preset named '{args.name}'. Saved presets: {presets or '(none)'}.",
                preview="Unknown preset",
                is_error=True,
            )
    if not script:
        return ToolResult(
            content="Pass a `script` (inline Python) or a saved preset `name`.",
            preview="No script",
            is_error=True,
        )

    workflow_id = f"wf-{uuid4().hex[:10]}"
    title = args.title or args.name or "workflow"
    emit = ctx.io.emit
    if emit:
        await emit(
            WorkflowStartedEvent(
                session_id=ctx.session_state.session_id,
                run_id=ctx.run.run_id,
                workflow_id=workflow_id,
                parent_tool_call_id=execution.tool_id,
                name=title,
                description=description or "",
                phases=args.phases,
            )
        )

    orchestra = Orchestra.for_ctx(ctx, parent_id=execution.tool_id, workflow_id=workflow_id, name=title)

    async def _finish(status: str, summary: str) -> None:
        if emit:
            await emit(
                WorkflowFinishedEvent(
                    session_id=ctx.session_state.session_id,
                    run_id=ctx.run.run_id,
                    workflow_id=workflow_id,
                    status=status,
                    summary=summary,
                    agent_count=orchestra.spawn_count,
                )
            )

    try:
        result = await run_script(orchestra, script, args.args)
    except asyncio.CancelledError:
        # User stopped the run. CancelledError is a BaseException, so without this
        # it would skip both excepts below and never settle the workflow row —
        # leaving it "running" with a free-running clock. Shield the settle so a
        # second cancellation mid-emit can't drop the terminal event, then re-raise
        # so the tool executor still sees the cancellation.
        await asyncio.shield(_finish("cancelled", "stopped by user"))
        raise
    except SyntaxError as exc:
        await _finish("failed", f"script did not compile: {exc}")
        # Self-correcting: hand back the exact compile error so the model can fix + retry.
        return ToolResult(
            content=f"Script did not compile: {exc}\nFix the Python and call the tool again.",
            preview="Script error",
            is_error=True,
        )
    except Exception as exc:
        await _finish("failed", str(exc)[:200])
        # Trimmed to the script's own frames with rebased line numbers, so the
        # model sees the line it wrote — the whole point of a self-correcting tool.
        tb = format_script_traceback(exc, script)
        return ToolResult(
            content=f"Workflow raised {type(exc).__name__}: {exc}\n\n{tb}\nFix the script and call again.",
            preview="Workflow failed",
            is_error=True,
        )

    await _finish("completed", "")
    return ToolResult(
        content=_render(result),
        preview=f"Ran workflow: {title}",
        data={"workflow": title, "workflow_id": workflow_id},
    )


WORKFLOW_DESCRIPTION = """\
Run a multi-agent workflow: either an inline `script` you author, or a saved preset by `name`.
Each agent runs in its own context window; you compose them.

PREFER A PRESET when one fits the task's shape — run it by `name` (pass parameters via `args`)
instead of hand-writing a script: `audit` (find -> verify -> rank issues over a target),
`investigate` (parallel readers -> a cited answer), `panel` (diverge into N takes -> judge ->
pick), `implement` (recon -> blueprint -> parallel builders -> adversarial review -> test gate,
for multi-file feature work from a spec). e.g. workflow(name="audit", args={"target":
"apps/server", "depth": "normal"}). Save any good run as a reusable preset with save_workflow.

When you DO author a script, plan before code: decide its 2-4 stages first, declare them in the
`phases` input (the UI shows the plan immediately), and structure the script around phase() calls
with the SAME titles. Keep each agent prompt TERSE and push specifics into `args` or let
agents DISCOVER them — do NOT hardcode long lists of ids/paths/PR numbers inline (it bloats
tokens and defeats caching). Pass args={"prs": [941, 956]} and read args["prs"]; don't paste the
numbers into every prompt. Terse applies to STATIC facts, not to piped context: agents share no
memory, so paste an upstream agent's full output (a blueprint, a brief) verbatim into the prompt
of every agent that depends on it — that text is the only contract parallel workers have. Pass `model` to an agent only when a cheaper/stronger configured tier
clearly fits a step (cheap finders, strong synthesis); default omits it and inherits the configured
workflow model (falls back to the chat model).

Each agent inherits ALL your tools by default (slack, gmail, files, web, etc.) — so for a
research/search task you just write agent("...") and it can use them. Give each agent a
tight, self-contained task; its final message IS the return value, so ask for the raw
answer (or JSON), no preamble.

In scope (no imports needed):
- await agent(task, *, schema=None, model=None, agent_type=None, system_prompt=None,
  tools=None, phase=None) -> the subagent's answer as a string, or a parsed object when `schema` is
  given (default: prose — only pass `schema` when you'll consume the fields in code, e.g.
  count votes or filter by a field). All keyword-only. `schema` is a plain dict shape, e.g.
  {"bugs": [{"file": "str", "line": "int"}]}. `agent_type` picks a ready-made type — each is
  a TOOL PROFILE plus a persona: "reviewer"/"explorer"/"planner"/"verifier" are READ-ONLY
  (read/search only, can't write or run bash — use for analysis), "builder" is full access
  (writes files, runs tools — use to make changes). `system_prompt` sets a custom persona
  (wins over agent_type's, but its tool profile still applies). `tools` is an OPTIONAL
  allowlist of tool NAMES to further RESTRICT this agent (e.g. tools=["slack_search",
  "read_file"]); omit it to keep the type's default access — do NOT pass it just to "grant"
  tools, they're already there.
- await parallel([...]) -> run agent() calls (or any awaitables) concurrently with a
  barrier; returns a list (a failed item is None). e.g. await parallel([agent(q) for q in qs]).
- await pipeline(items, stage1, stage2, ...) -> run each item through the stages with no
  barrier between items; each stage is `async (prev, item, index) -> next` (3 args), and a
  stage returning None drops that item. Returns the list of final results.
- phase(title) / log(msg) -> progress labels shown in the UI. phase() sets a GLOBAL current
  label that agents snapshot at call time — fine for top-level sequential code, but inside
  pipeline() stages (or any concurrently-running chains) it races: pass phase="..." to each
  agent() there explicitly.
- budget -> the run's token pool: budget.total (the ceiling, or None if uncapped),
  budget.spent() (output tokens used so far across the whole run), budget.remaining()
  (total - spent, or inf if uncapped). Scale fan-out to it: a loop guards on
  `while budget.total and budget.remaining() > 50_000: ...`; once spent reaches total,
  further agent() spawns are denied. Reusable sub-routines are just `async def` helpers in
  your script — define and call them like normal Python.
- args -> the dict you passed in. `json` is available. End with `return <result>`.

Patterns:
- fan-out then synthesize: parts = await parallel([agent(p) for p in prompts]); return await agent("synthesize: " + json.dumps(parts))
- adversarial verify: votes = await parallel([agent("Refute, default refuted=true: " + claim, schema={"refuted": "bool"}) for _ in range(3)]); keep if most say not refuted
- loop until done: while not done: r = await agent(...); update done
- deep build: recon readers -> one architect pins every cross-file contract in a blueprint ->
  parallel builders each given the FULL blueprint (schema: files_changed + deviations) ->
  review lenses -> skeptics refute each finding -> fixer -> final test gate (the `implement`
  preset is this shape — compose your own variants for other deep work)

Example (called with phases=["research", "synthesize"], args={"questions": [...]}):
  phase("research")
  notes = await parallel([
      agent(f"Research: {q}. Return key facts.", schema={"facts": ["str"]})
      for q in args["questions"]
  ])
  phase("synthesize")
  return await agent("Write a brief from these notes:\\n" + json.dumps(notes))

Use for complex, high-value, multi-step tasks worth several agents. Not for routine
single-step work (it costs far more tokens). Match depth to stakes: a focused question is one
phase and a few agents, but "implement X" / "audit thoroughly" earns the full plan -> build ->
adversarial review -> verify arc — don't write a shallow two-phase script for deep work. On a
script error the exact error comes back — fix it and call again."""

workflow_tool = tool(
    display_name="Workflow",
    description=WORKFLOW_DESCRIPTION,
    input_model=WorkflowInput,
    policy=ToolPolicy(action=ToolAction.EXECUTE, scope=ToolScope.INTERNAL, permissions=frozenset({"skill_registry"})),
    execute=run_workflow,
    # "workflow" (not "agent") so the desktop renders it as a workflow card from
    # the tool call itself — independent of the streamed workflow-domain events.
    kind="workflow",
)


async def run_save_workflow(execution: ToolExecution, args: SaveWorkflowInput) -> ToolResult:
    svc = execution.ctx.services.get("skill_service")
    if svc is None:
        return ToolResult(content="Error: skill service not available.", preview="Unavailable", is_error=True)
    try:
        meta = svc.save_workflow(args.name, args.description, args.script)
    except ValueError as exc:
        return ToolResult(content=f"Could not save preset: {exc}", preview="Save failed", is_error=True)
    return ToolResult(
        content=f"Saved workflow preset '{meta.name}'. Run it with workflow(name=\"{meta.name}\", args={{...}}).",
        preview=f"Saved preset {meta.name}",
    )


save_workflow_tool = tool(
    display_name="Save Workflow",
    description="Save a workflow script as a reusable preset (a workflow-skill at ~/.ntrp/skills/<name>/). "
    "Afterwards run it with workflow(name=...). Use when the user asks to save/remember a workflow they liked.",
    input_model=SaveWorkflowInput,
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL, permissions=frozenset({"skill_service"})),
    execute=run_save_workflow,
)
