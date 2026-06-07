import json
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from ntrp.events.sse import WorkflowFinishedEvent, WorkflowStartedEvent
from ntrp.orchestra.engine import Orchestra
from ntrp.orchestra.registry import registry
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope


class WorkflowInput(BaseModel):
    name: str = Field(description="Name of the registered workflow to run.")
    args: dict = Field(
        default_factory=dict,
        description="Arguments for the workflow, validated against its params.",
    )


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

    wf = registry.get(args.name)
    if wf is None:
        names = ", ".join(sorted(w.meta.name for w in registry.list_all())) or "(none registered)"
        return ToolResult(
            content=f"Unknown workflow '{args.name}'. Available: {names}",
            preview="Unknown workflow",
            is_error=True,
        )

    try:
        params = wf.meta.params.model_validate(args.args)
    except ValidationError as exc:
        return ToolResult(content=f"Invalid args for '{args.name}': {exc}", preview="Invalid args", is_error=True)

    workflow_id = f"wf-{uuid4().hex[:10]}"
    emit = ctx.io.emit
    if emit:
        await emit(
            WorkflowStartedEvent(
                session_id=ctx.session_state.session_id,
                run_id=ctx.run.run_id,
                workflow_id=workflow_id,
                parent_tool_call_id=execution.tool_id,
                name=wf.meta.name,
                description=wf.meta.description,
            )
        )
    orchestra = Orchestra.for_ctx(ctx, parent_id=execution.tool_id, workflow_id=workflow_id, name=wf.meta.name)
    try:
        result = await wf.run(orchestra, params)
    except Exception as exc:
        if emit:
            await emit(
                WorkflowFinishedEvent(
                    session_id=ctx.session_state.session_id,
                    run_id=ctx.run.run_id,
                    workflow_id=workflow_id,
                    status="failed",
                    summary=str(exc)[:200],
                    agent_count=orchestra.spawn_count,
                )
            )
        return ToolResult(content=f"Workflow '{args.name}' failed: {exc}", preview="Workflow failed", is_error=True)
    if emit:
        await emit(
            WorkflowFinishedEvent(
                session_id=ctx.session_state.session_id,
                run_id=ctx.run.run_id,
                workflow_id=workflow_id,
                status="completed",
                summary="",
                agent_count=orchestra.spawn_count,
            )
        )
    return ToolResult(
        content=_render(result),
        preview=f"Ran workflow {args.name}",
        data={"workflow": args.name, "workflow_id": workflow_id},
    )


WORKFLOW_DESCRIPTION = (
    "Run a registered multi-step workflow that deterministically orchestrates "
    "subagents (parallel fan-out + pipelines) and returns a structured result. "
    "Provide the workflow `name` and its `args`. On an unknown name, the available "
    "workflows are listed back."
)

workflow_tool = tool(
    display_name="Workflow",
    description=WORKFLOW_DESCRIPTION,
    input_model=WorkflowInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=run_workflow,
    kind="agent",
)
