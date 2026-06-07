import json
import traceback
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ntrp.events.sse import WorkflowFinishedEvent, WorkflowStartedEvent
from ntrp.orchestra.dynamic import run_script
from ntrp.orchestra.engine import Orchestra
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope


class WorkflowInput(BaseModel):
    script: str = Field(
        description="Python orchestration script. Uses await agent()/parallel()/pipeline(), "
        "phase(), log(), `args`, `json`, and `return`s a result. See the tool description."
    )
    title: str = Field(default="workflow", description="Short label for this run, shown in the UI.")
    args: dict = Field(default_factory=dict, description="Values exposed to the script as `args`.")


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

    workflow_id = f"wf-{uuid4().hex[:10]}"
    title = args.title or "workflow"
    emit = ctx.io.emit
    if emit:
        await emit(
            WorkflowStartedEvent(
                session_id=ctx.session_state.session_id,
                run_id=ctx.run.run_id,
                workflow_id=workflow_id,
                parent_tool_call_id=execution.tool_id,
                name=title,
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
        result = await run_script(orchestra, args.script, args.args)
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
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=4))
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
Run a custom multi-agent workflow you author on the fly — a harness built for this task.
Pass a Python `script` that orchestrates subagents and returns a result. Each agent runs
in its own context window; you compose them.

In scope (no imports needed):
- await agent(task, schema=None, model=None) -> the subagent's answer as a string, or a
  parsed object when `schema` is given. `schema` is a plain dict describing the JSON shape,
  e.g. {"bugs": [{"file": "str", "line": "int", "issue": "str"}]}.
- await parallel([...]) -> run agent() calls (or any awaitables) concurrently; returns a
  list (a failed item is None). e.g. await parallel([agent(q) for q in questions]).
- phase(title) / log(msg) -> progress labels shown in the UI.
- args -> the dict you passed in. `json` is available. End with `return <result>`.

Patterns:
- fan-out then synthesize: parts = await parallel([agent(p) for p in prompts]); return await agent("synthesize: " + json.dumps(parts))
- adversarial verify: votes = await parallel([agent("Refute, default refuted=true: " + claim, schema={"refuted": "bool"}) for _ in range(3)]); keep if most say not refuted
- loop until done: while not done: r = await agent(...); update done

Example:
  phase("research")
  notes = await parallel([
      agent(f"Research: {q}. Return key facts.", schema={"facts": ["str"]})
      for q in args["questions"]
  ])
  phase("synthesize")
  return await agent("Write a brief from these notes:\\n" + json.dumps(notes))

Use for complex, high-value, multi-step tasks worth several agents. Not for routine
single-step work (it costs far more tokens). On a script error the exact error comes
back — fix it and call again."""

workflow_tool = tool(
    display_name="Workflow",
    description=WORKFLOW_DESCRIPTION,
    input_model=WorkflowInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=run_workflow,
    kind="agent",
)
