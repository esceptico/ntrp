import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from coolname import generate_slug

from ntrp.agent import Agent, Result, Role, Usage
from ntrp.context.models import SessionState
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import build_system_prompt
from ntrp.events.internal import RunCompleted
from ntrp.events.sse import AutomationProgressEvent, ToolCallEvent, ToolResultEvent, agent_event_to_sse
from ntrp.server.bus import SessionBus
from ntrp.skills.registry import SkillRegistry
from ntrp.tools.core.context import ApprovalControls
from ntrp.tools.deferred import build_deferred_tools_prompt_for_schemas
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor


@dataclass(frozen=True)
class OperatorDeps:
    executor: ToolExecutor
    config: AgentConfig
    source_details: dict[str, dict]
    create_session: Callable[[], SessionState]
    notifiers: list[dict[str, str]]
    enqueue_run_completed: Callable[[RunCompleted], Awaitable[bool]] | None = None
    skill_registry: SkillRegistry | None = None
    memory_records: object | None = None


@dataclass(frozen=True)
class RunRequest:
    prompt: str
    auto_approve: bool
    source_id: str
    prompt_suffix: str = ""
    model: str | None = None
    skip_approvals: bool = False
    automation_id: str | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    output: str | None
    usage: Usage


# Below this many chars of prompt there is nothing worth a scoped recall.
_MEMORY_RECALL_FLOOR = 12


async def _retrieve_memory_context(memory_records: object | None, prompt: str) -> str | None:
    """Pinned records for an operator/automation run.

    Automation runs act on behalf of the principal; they inject the durable
    pinned records (zero-LLM, zero per-run vector). Skips on trivial input.
    """
    if memory_records is None or not prompt or len(prompt.strip()) < _MEMORY_RECALL_FLOOR:
        return None
    try:
        records = await memory_records.list(pinned_only=True, limit=20)
    except Exception:
        return None
    if not records:
        return None
    return "## Pinned\n\n" + "\n".join(f"- [{r.kind}] {r.text}" for r in records)


async def _prepare(deps: OperatorDeps, request: RunRequest) -> tuple[Agent, list[dict], str, str]:
    run_id = generate_slug(2)
    session_state = deps.create_session()

    memory_context = await _retrieve_memory_context(deps.memory_records, request.prompt)

    executor = deps.executor
    tools = executor.get_tools() if request.auto_approve else executor.get_tools(read_only=True)

    agent_config = deps.config
    if request.model:
        agent_config = replace(deps.config, model=request.model)

    deferred_tools_context = (
        build_deferred_tools_prompt_for_schemas(executor.registry, frozenset(executor.tool_services), tools)
        if agent_config.deferred_tools
        else None
    )

    system_prompt = build_system_prompt(
        source_details=deps.source_details,
        memory_context=memory_context,
        directives=load_directives(),
        notifiers=deps.notifiers or None,
        deferred_tools_context=deferred_tools_context,
    )
    system_prompt += request.prompt_suffix

    agent = create_agent(
        executor=executor,
        config=agent_config,
        tools=tools,
        session_state=session_state,
        run_id=run_id,
        approval_controls=ApprovalControls(skip_approvals=request.skip_approvals),
    )

    messages = [
        {"role": Role.SYSTEM, "content": system_prompt},
        {"role": Role.USER, "content": request.prompt},
    ]

    return agent, messages, run_id, session_state.session_id


async def _publish_completed(
    deps: OperatorDeps,
    run_id: str,
    session_id: str,
    messages: list,
    usage: Usage,
    result: str | None,
) -> None:
    event = RunCompleted(
        run_id=run_id,
        session_id=session_id,
        messages=tuple(messages),
        usage=usage,
        result=result,
    )
    if deps.enqueue_run_completed:
        await deps.enqueue_run_completed(event)


async def run_agent(deps: OperatorDeps, request: RunRequest) -> RunResult:
    agent, messages, run_id, session_id = await _prepare(deps, request)

    agent_result = await agent.run(messages)
    await _publish_completed(deps, run_id, session_id, messages, agent_result.usage, agent_result.text)

    return RunResult(run_id=run_id, output=agent_result.text, usage=agent_result.usage)


async def run_agent_streaming(
    deps: OperatorDeps,
    request: RunRequest,
    bus: SessionBus,
    task_id: str,
) -> RunResult:
    agent, messages, run_id, session_id = await _prepare(deps, request)

    result_text: str | None = None
    usage = Usage()
    gen = agent.stream(messages)
    try:
        async for item in gen:
            if isinstance(item, Result):
                result_text = item.text
                usage = item.usage
            else:
                sse = agent_event_to_sse(item)
                if isinstance(sse, ToolCallEvent):
                    label = sse.display_name or sse.tool_call_name
                    await bus.emit(AutomationProgressEvent(task_id=task_id, status=f"{label}..."))
                elif isinstance(sse, ToolResultEvent):
                    label = sse.display_name or sse.name
                    status = f"{label}: {sse.preview}" if sse.preview else label
                    await bus.emit(AutomationProgressEvent(task_id=task_id, status=status))
    except asyncio.CancelledError:
        pass

    await _publish_completed(deps, run_id, session_id, messages, usage, result_text)

    return RunResult(run_id=run_id, output=result_text, usage=usage)
