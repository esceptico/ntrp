import asyncio
from dataclasses import dataclass
from datetime import datetime

from ntrp.channel import Channel
from ntrp.context.models import SessionData, SessionState
from ntrp.core.agent import Agent
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import INIT_INSTRUCTION, build_system_blocks
from ntrp.events.internal import RunCompleted, RunStarted
from ntrp.events.sse import (
    BackgroundedEvent,
    DoneEvent,
    ErrorEvent,
    SessionInfoEvent,
    TextEvent,
    ThinkingEvent,
)
from ntrp.llm.models import Provider, get_model
from ntrp.logging import get_logger
from ntrp.memory.formatting import format_session_memory
from ntrp.server.bus import SessionBus
from ntrp.server.runtime import Runtime
from ntrp.server.state import RunRegistry, RunState, RunStatus
from ntrp.server.stream import run_agent_loop
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.tools.core.context import IOBridge
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)

INIT_AUTO_APPROVE = {"remember", "forget"}


@dataclass
class ChatContext:
    run: RunState
    session_state: SessionState
    is_init: bool
    executor: ToolExecutor
    tools: list[dict]
    config: AgentConfig
    channel: Channel
    available_sources: list[str]
    source_errors: dict[str, str]
    session_service: SessionService
    run_registry: RunRegistry


def expand_skill_command(message: str, registry: SkillRegistry) -> tuple[str, bool]:
    stripped = message.strip()
    if not stripped.startswith("/"):
        return message, False
    parts = stripped[1:].split(None, 1)
    skill_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    body = registry.load_body(skill_name)
    if body is None:
        return message, False
    expanded = f'<skill name="{skill_name}">\n{body}\n</skill>'
    if args:
        expanded += f"\n\nUser request: {args}"
    return expanded, True


def _is_anthropic(model: str) -> bool:
    return get_model(model).provider == Provider.ANTHROPIC


async def _resolve_session(runtime: Runtime) -> SessionData:
    data = await runtime.session_service.load()
    if data and data.messages and len(data.messages) >= 2:
        return data
    return SessionData(runtime.session_service.create(), [])


def build_user_content(text: str, images: list[dict] | None = None) -> str | list[dict]:
    if not images:
        return text
    blocks: list[dict] = []
    if text:
        blocks.append({"type": "text", "text": text})
    blocks.extend({"type": "image", "media_type": img["media_type"], "data": img["data"]} for img in images)
    return blocks


async def _prepare_messages(
    runtime: Runtime,
    messages: list[dict],
    user_message: str,
    last_activity: datetime | None = None,
    images: list[dict] | None = None,
) -> list[dict]:
    memory_context = None
    if runtime.memory:
        observations, user_facts = await runtime.memory.get_context()
        memory_context = format_session_memory(observations=observations, user_facts=user_facts)

    skills_context = runtime.skill_registry.to_prompt_xml() if runtime.skill_registry else None
    directives = load_directives()

    notifier_names = list(runtime.notifier_service.notifiers) if runtime.notifier_service else None

    system_blocks = build_system_blocks(
        source_details=runtime.source_mgr.get_details(),
        last_activity=last_activity,
        memory_context=memory_context,
        skills_context=skills_context,
        directives=directives,
        notifier_names=notifier_names,
        use_cache_control=_is_anthropic(runtime.config.chat_model),
    )

    if not messages:
        messages = [{"role": "system", "content": system_blocks}]
    elif isinstance(messages[0], dict) and messages[0]["role"] == "system":
        messages[0]["content"] = system_blocks
    else:
        messages.insert(0, {"role": "system", "content": system_blocks})

    messages.append({"role": "user", "content": build_user_content(user_message, images)})

    return messages


async def prepare_chat(
    runtime: Runtime,
    message: str,
    skip_approvals: bool = False,
    session_id: str | None = None,
    images: list[dict] | None = None,
) -> ChatContext:
    registry = runtime.run_registry

    if session_id:
        session_data = await runtime.session_service.load(session_id)
        if not session_data:
            session_data = SessionData(runtime.session_service.create(), [])
    else:
        session_data = await _resolve_session(runtime)
    session_state = session_data.state
    session_state.skip_approvals = skip_approvals
    messages = session_data.messages

    user_message = message
    is_init = user_message.strip().lower() == "/init"
    if is_init:
        user_message = INIT_INSTRUCTION
    elif runtime.skill_registry:
        user_message, _ = expand_skill_command(user_message, runtime.skill_registry)

    name_candidate = message.strip() or ("[image]" if images else "")
    if not session_state.name and not is_init and name_candidate and not name_candidate.startswith("/"):
        session_state.name = name_candidate[:50]

    messages = await _prepare_messages(
        runtime, messages, user_message, last_activity=session_state.last_activity, images=images
    )

    run = registry.create_run(session_state.session_id)
    run.messages = messages

    return ChatContext(
        run=run,
        session_state=session_state,
        is_init=is_init,
        executor=runtime.executor,
        tools=runtime.executor.get_tools(),
        config=AgentConfig.from_config(runtime.config),
        channel=runtime.channel,
        available_sources=runtime.get_available_sources(),
        source_errors=runtime.get_source_errors(),
        session_service=runtime.session_service,
        run_registry=runtime.run_registry,
    )


async def _drain_backgrounded(
    gen,
    agent: Agent,
    ctx: ChatContext,
) -> None:
    """Continue draining an agent stream silently after the run was backgrounded."""
    agent.ctx.session_state.skip_approvals = True
    agent.ctx.io.emit = None
    try:
        async for _ in gen:
            pass
    except asyncio.CancelledError:
        pass
    except Exception:
        _logger.exception("Backgrounded drain failed (run_id=%s)", ctx.run.run_id)
    finally:
        if agent.inject_queue:
            agent.messages.extend(agent.inject_queue)
            agent.inject_queue.clear()
        ctx.run.messages = agent.messages
        ctx.run.usage = agent.usage
        last_tokens = getattr(agent, "_last_input_tokens", None)
        metadata = {"last_input_tokens": last_tokens} if last_tokens is not None else None
        await ctx.session_service.save(ctx.session_state, agent.messages, metadata=metadata)


async def run_chat(ctx: ChatContext, bus: SessionBus) -> None:
    """Run agent loop, push all events to bus. Fire-and-forget."""
    run = ctx.run
    session_state = ctx.session_state

    run.approval_queue = asyncio.Queue()

    await bus.emit(
        SessionInfoEvent(
            session_id=session_state.session_id,
            run_id=run.run_id,
            sources=ctx.available_sources,
            source_errors=ctx.source_errors,
            skip_approvals=session_state.skip_approvals,
            session_name=session_state.name or "",
        )
    )

    await bus.emit(ThinkingEvent(status="processing..."))
    ctx.channel.publish(RunStarted(run_id=run.run_id, session_id=session_state.session_id))

    agent: Agent | None = None
    result: str | None = None
    try:
        agent = create_agent(
            executor=ctx.executor,
            config=ctx.config,
            tools=ctx.tools,
            system_prompt=ctx.run.messages[0]["content"] if ctx.run.messages else [],
            session_state=session_state,
            channel=ctx.channel,
            run_id=run.run_id,
            io=IOBridge(
                approval_queue=run.approval_queue,
            ),
            extra_auto_approve=INIT_AUTO_APPROVE if ctx.is_init else None,
        )

        # Share inject_queue and mark running only after wiring is complete
        run.inject_queue = agent.inject_queue
        run.status = RunStatus.RUNNING
        run_finished = False

        async def _on_bg_result(messages: list[dict]) -> None:
            if not run_finished:
                agent.inject_queue.extend(messages)
            else:
                run.messages.extend(messages)
                await ctx.session_service.save(session_state, run.messages)

        agent.ctx.background_tasks.on_result = _on_bg_result

        result, bg_gen = await run_agent_loop(ctx, agent, bus)

        if bg_gen is not None:
            # Backgrounded: unlock UI, drain agent silently
            await bus.emit(BackgroundedEvent(run_id=run.run_id))
            ctx.run_registry.complete_run(run.run_id)
            run_finished = True
            asyncio.create_task(_drain_backgrounded(bg_gen, agent, ctx))
            return

        if result is None:
            return  # Cancelled

        if agent:
            run.usage = agent.usage
            run.messages = agent.messages

        if result:
            await bus.emit(TextEvent(content=result))

        await bus.emit(DoneEvent(run_id=run.run_id, usage=run.usage.to_dict()))
        ctx.run_registry.complete_run(run.run_id)

    except Exception as e:
        _logger.exception("Chat failed (run_id=%s, session_id=%s)", run.run_id, session_state.session_id)
        await bus.emit(ErrorEvent(message=str(e), recoverable=False))
        run.status = RunStatus.ERROR
        ctx.run_registry.cleanup_old_runs()

    finally:
        if not run.backgrounded:
            if agent:
                if run.status in (RunStatus.CANCELLED, RunStatus.ERROR) or run.cancelled:
                    agent.ctx.background_tasks.cancel_all()
                if agent.inject_queue:
                    agent.messages.extend(agent.inject_queue)
                    agent.inject_queue.clear()
                run.usage = agent.usage
                run.messages = agent.messages
            run_finished = True
            last_tokens = getattr(agent, "_last_input_tokens", None) if agent else None
            metadata = {"last_input_tokens": last_tokens} if last_tokens is not None else None
            await ctx.session_service.save(session_state, run.messages, metadata=metadata)
            ctx.channel.publish(
                RunCompleted(
                    run_id=run.run_id,
                    session_id=session_state.session_id,
                    messages=tuple(run.messages),
                    usage=run.usage,
                    result=result,
                )
            )
