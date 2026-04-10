from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from coolname import generate_slug

from ntrp.agent import Result, Role, Usage
from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import build_system_prompt
from ntrp.events.internal import RunCompleted, RunStarted
from ntrp.events.sse import agent_event_to_sse
from ntrp.memory.facts import FactMemory
from ntrp.memory.formatting import format_session_memory
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor

if TYPE_CHECKING:
    from ntrp.server.bus import SessionBus


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
    skip_approvals: bool = False


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
    session_state.skip_approvals = request.skip_approvals
    executor = deps.executor
    tools = executor.get_tools() if request.writable else executor.get_tools(mutates=False)

    agent_config = deps.config
    if request.model:
        agent_config = replace(deps.config, model=request.model)

    agent = create_agent(
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
    agent_result = await agent.run(messages)
    deps.channel.publish(
        RunCompleted(
            run_id=run_id,
            session_id=session_state.session_id,
            messages=tuple(messages),
            usage=agent_result.usage,
            result=agent_result.text,
        )
    )

    return RunResult(run_id=run_id, output=agent_result.text, usage=agent_result.usage)


async def run_agent_streaming(deps: OperatorDeps, request: RunRequest, bus: SessionBus) -> RunResult:
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
    session_state.skip_approvals = request.skip_approvals
    executor = deps.executor
    tools = executor.get_tools() if request.writable else executor.get_tools(mutates=False)

    agent_config = deps.config
    if request.model:
        agent_config = replace(deps.config, model=request.model)

    agent = create_agent(
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
                if sse:
                    await bus.emit(sse)
                    await asyncio.sleep(0)
    except asyncio.CancelledError:
        pass

    deps.channel.publish(
        RunCompleted(
            run_id=run_id,
            session_id=session_state.session_id,
            messages=tuple(messages),
            usage=usage,
            result=result_text,
        )
    )

    return RunResult(run_id=run_id, output=result_text, usage=usage)
