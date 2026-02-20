import secrets
from collections.abc import Callable
from dataclasses import dataclass

from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import build_system_prompt
from ntrp.events.internal import RunCompleted, RunStarted
from ntrp.memory.facts import FactMemory
from ntrp.memory.formatting import format_session_memory
from ntrp.notifiers.base import Notifier
from ntrp.notifiers.log_store import NotificationLogStore
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor
from ntrp.tools.notify import NotifyTool
from ntrp.usage import Usage


@dataclass(frozen=True)
class OperatorDeps:
    executor: ToolExecutor
    memory: FactMemory | None
    config: AgentConfig
    channel: Channel
    source_details: dict[str, dict]
    create_session: Callable[[], SessionState]
    notifiers: dict[str, Notifier]
    notification_log: NotificationLogStore


@dataclass(frozen=True)
class RunRequest:
    prompt: str
    prompt_suffix: str
    writable: bool
    notifiers: list[str]
    source_id: str


@dataclass(frozen=True)
class RunResult:
    run_id: str
    output: str | None
    usage: Usage


async def run_agent(deps: OperatorDeps, request: RunRequest) -> RunResult:
    run_id = secrets.token_hex(4)

    memory_context = None
    if deps.memory:
        observations, user_facts = await deps.memory.get_context()
        memory_context = format_session_memory(observations=observations, user_facts=user_facts)

    system_prompt = build_system_prompt(
        source_details=deps.source_details,
        memory_context=memory_context,
        directives=load_directives(),
    )
    system_prompt += request.prompt_suffix

    session_state = deps.create_session()
    executor = deps.executor
    tools = executor.get_tools() if request.writable else executor.get_tools(mutates=False)

    if request.notifiers:
        resolved = [deps.notifiers[name] for name in request.notifiers if name in deps.notifiers]
        if resolved:
            notify_tool = NotifyTool(resolved, deps.notification_log, request.source_id)
            run_registry = executor.registry.copy_with(notify_tool)
            executor = executor.with_registry(run_registry)
            tools = [*tools, notify_tool.to_dict()]

    agent = create_agent(
        executor=executor,
        config=deps.config,
        tools=tools,
        system_prompt=system_prompt,
        session_state=session_state,
        memory=deps.memory,
        channel=deps.channel,
        run_id=run_id,
    )

    deps.channel.publish(RunStarted(run_id=run_id, session_id=session_state.session_id))
    output: str | None = None
    try:
        output = await agent.run(request.prompt)
    finally:
        deps.channel.publish(RunCompleted(run_id=run_id, usage=agent.usage, result=output))

    return RunResult(run_id=run_id, output=output, usage=agent.usage)
