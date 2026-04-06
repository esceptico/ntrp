from collections.abc import Callable
from dataclasses import dataclass, replace

from coolname import generate_slug

from ntrp.agent import Role, Usage
from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import build_system_prompt
from ntrp.events.internal import RunCompleted, RunStarted
from ntrp.memory.facts import FactMemory
from ntrp.memory.formatting import format_session_memory
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor


@dataclass(frozen=True)
class OperatorDeps:
    executor: ToolExecutor
    memory: FactMemory | None
    config: AgentConfig
    channel: Channel
    source_details: dict[str, dict]
    create_session: Callable[[], SessionState]
    notifiers: list[dict[str, str]]


@dataclass(frozen=True)
class RunRequest:
    prompt: str
    writable: bool
    source_id: str
    prompt_suffix: str = ""
    model: str | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    output: str | None
    usage: Usage


async def run_agent(deps: OperatorDeps, request: RunRequest) -> RunResult:
    run_id = generate_slug(2)

    memory_context = None
    if deps.memory:
        observations, user_facts = await deps.memory.get_context()
        memory_context = format_session_memory(observations=observations, user_facts=user_facts)

    system_prompt = build_system_prompt(
        source_details=deps.source_details,
        memory_context=memory_context,
        directives=load_directives(),
        notifiers=deps.notifiers or None,
    )
    system_prompt += request.prompt_suffix

    session_state = deps.create_session()
    executor = deps.executor
    tools = executor.get_tools() if request.writable else executor.get_tools(mutates=False)

    agent_config = deps.config
    if request.model:
        agent_config = replace(deps.config, model=request.model)

    agent, callbacks, _ = create_agent(
        executor=executor,
        config=agent_config,
        tools=tools,
        session_state=session_state,
        channel=deps.channel,
        run_id=run_id,
    )

    messages = [
        {"role": Role.SYSTEM, "content": system_prompt},
        {"role": Role.USER, "content": request.prompt},
    ]

    deps.channel.publish(RunStarted(run_id=run_id, session_id=session_state.session_id))
    output: str | None = None
    try:
        run_result = await agent.run(messages)
        output = run_result.text
    finally:
        deps.channel.publish(
            RunCompleted(
                run_id=run_id,
                session_id=session_state.session_id,
                messages=tuple(messages),
                usage=callbacks.usage,
                result=output,
            )
        )

    return RunResult(run_id=run_id, output=output, usage=callbacks.usage)
