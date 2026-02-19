from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.core.factory import create_agent
from ntrp.core.prompts import build_system_prompt
from ntrp.events.internal import RunCompleted, RunStarted
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.formatting import format_session_memory
from ntrp.notifiers.base import Notifier
from ntrp.notifiers.log_store import NotificationLogStore
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor
from ntrp.tools.notify import NotifyTool

_logger = get_logger(__name__)


@dataclass(frozen=True)
class OperatorDeps:
    executor: ToolExecutor
    memory: Callable[[], FactMemory | None]
    get_model: Callable[[], str]
    max_depth: int
    channel: Channel
    source_details: Callable[[], dict[str, dict]]
    create_session: Callable[[], SessionState]
    get_notifiers: Callable[[], dict[str, Notifier]]
    notification_log: NotificationLogStore
    get_explore_model: Callable[[], str | None]


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
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


async def run_agent(deps: OperatorDeps, request: RunRequest) -> RunResult:
    run_id = str(uuid4())[:8]

    memory = deps.memory()
    memory_context = None
    if memory:
        observations, user_facts = await memory.get_context()
        memory_context = format_session_memory(observations=observations, user_facts=user_facts)

    system_prompt = build_system_prompt(
        source_details=deps.source_details(),
        memory_context=memory_context,
        directives=load_directives(),
    )
    system_prompt += request.prompt_suffix

    session_state = deps.create_session()
    executor = deps.executor
    tools = executor.get_tools() if request.writable else executor.get_tools(mutates=False)

    if request.notifiers:
        notifier_registry = deps.get_notifiers()
        resolved = [notifier_registry[name] for name in request.notifiers if name in notifier_registry]
        if resolved:
            notify_tool = NotifyTool(resolved, deps.notification_log, request.source_id)
            run_registry = executor.registry.copy_with(notify_tool)
            executor = executor.with_registry(run_registry)
            tools = [*tools, notify_tool.to_dict()]

    agent = create_agent(
        executor=executor,
        model=deps.get_model(),
        tools=tools,
        system_prompt=system_prompt,
        session_state=session_state,
        memory=memory,
        channel=deps.channel,
        max_depth=deps.max_depth,
        explore_model=deps.get_explore_model(),
        run_id=run_id,
    )

    deps.channel.publish(RunStarted(run_id=run_id, session_id=session_state.session_id))
    output: str | None = None
    try:
        output = await agent.run(request.prompt)
    finally:
        deps.channel.publish(
            RunCompleted(
                run_id=run_id,
                prompt_tokens=agent.total_input_tokens,
                completion_tokens=agent.total_output_tokens,
                cache_read_tokens=agent.total_cache_read_tokens,
                cache_write_tokens=agent.total_cache_write_tokens,
                result=output,
            )
        )

    return RunResult(
        run_id=run_id,
        output=output,
        prompt_tokens=agent.total_input_tokens,
        completion_tokens=agent.total_output_tokens,
        cache_read_tokens=agent.total_cache_read_tokens,
        cache_write_tokens=agent.total_cache_write_tokens,
    )
