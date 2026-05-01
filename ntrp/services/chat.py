import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ntrp.agent import Agent, Role
from ntrp.constants import CONVERSATION_GAP_THRESHOLD
from ntrp.context.models import SessionData, SessionState
from ntrp.core.content import ContextContent, ImageContent, TextContent
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import INIT_INSTRUCTION, build_system_blocks
from ntrp.core.usage_tracker import UsageTracker
from ntrp.events.internal import RunCompleted
from ntrp.events.sse import (
    MessageIngestedEvent,
    RunBackgroundedEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextEvent,
    ThinkingEvent,
)
from ntrp.llm.models import Provider, get_model
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.formatting import format_session_memory_render
from ntrp.memory.learning_context import get_approved_learning_context
from ntrp.memory.prefetch import prefetch_memory_context
from ntrp.notifiers.service import NotifierService
from ntrp.server.bus import BusRegistry, SessionBus
from ntrp.server.state import RunRegistry, RunState, RunStatus
from ntrp.server.stream import run_agent_loop
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.tools.core.context import IOBridge
from ntrp.tools.directives import load_directives
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)

INIT_AUTO_APPROVE = {"remember", "forget"}


@dataclass(frozen=True)
class ChatDeps:
    chat_model: str
    agent_config: AgentConfig
    executor: ToolExecutor
    session_service: SessionService
    run_registry: RunRegistry
    available_integrations: list[str]
    integration_errors: dict[str, str]
    enqueue_run_completed: Callable[[RunCompleted], Awaitable[bool]] | None = None
    memory: FactMemory | None = None
    skill_registry: SkillRegistry | None = None
    notifier_service: NotifierService | None = None


@dataclass
class ChatContext:
    run: RunState
    session_state: SessionState
    is_init: bool
    executor: ToolExecutor
    tools: list[dict]
    config: AgentConfig
    available_integrations: list[str]
    integration_errors: dict[str, str]
    session_service: SessionService
    run_registry: RunRegistry
    enqueue_run_completed: Callable[[RunCompleted], Awaitable[bool]] | None = None


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
    meta = registry.get(skill_name)
    body = body.replace("<skill_path>", str(meta.path)) if meta else body
    path_attr = f' path="{meta.path}"' if meta else ""
    expanded = f'<skill name="{skill_name}"{path_attr}>\n{body}\n</skill>'
    if args:
        expanded += f"\n\nUser request: {args}"
    return expanded, True


def _is_anthropic(model: str) -> bool:
    return get_model(model).provider == Provider.ANTHROPIC


async def _resolve_session(deps: ChatDeps) -> SessionData:
    data = await deps.session_service.load()
    if data and data.messages and len(data.messages) >= 2:
        return data
    return SessionData(deps.session_service.create(), [])


def build_user_content(
    text: str,
    images: list[dict] | None = None,
    context: list[dict] | None = None,
) -> str | list[dict]:
    if not images and not context:
        return text
    blocks = []
    if context:
        blocks.extend(ContextContent(**ctx).model_dump(exclude_none=True) for ctx in context)
    if text:
        blocks.append(TextContent(text=text).model_dump())
    if images:
        blocks.extend(ImageContent(**img).model_dump() for img in images)
    return blocks


def _time_gap_note(last_activity: datetime) -> dict | None:
    gap = (datetime.now(UTC) - last_activity).total_seconds()
    if gap < CONVERSATION_GAP_THRESHOLD:
        return None
    hours = gap / 3600
    if hours < 1:
        elapsed = f"{int(gap / 60)} minutes"
    elif hours < 24:
        elapsed = f"{hours:.1f} hours"
    else:
        elapsed = f"{hours / 24:.1f} days"
    return {"content_type": "time_since_last_message", "content": elapsed}


def _retain_user_content(messages: list[dict]) -> list[dict]:
    result = []
    for msg in messages:
        if msg.get("role") == Role.USER and isinstance(msg.get("content"), list):
            msg = {**msg, "content": [b for b in msg["content"] if b.get("type") != "context"]}
        result.append(msg)
    return result


async def _prepare_messages(
    deps: ChatDeps,
    messages: list[dict],
    user_message: str,
    last_activity: datetime | None = None,
    images: list[dict] | None = None,
    context: list[dict] | None = None,
) -> list[dict]:
    memory_context = None
    if deps.memory:
        session_memory = await deps.memory.get_session_memory()
        session_render = format_session_memory_render(
            profile_facts=session_memory.profile_facts,
            observations=session_memory.observations,
            user_facts=session_memory.user_facts,
        )
        prefetch_context = await prefetch_memory_context(
            deps.memory,
            user_message,
            session_memory,
            source="chat_prefetch",
        )
        memory_parts = []
        if session_render is not None:
            memory_parts.append(session_render.text)
        if prefetch_context is not None:
            memory_parts.append(f"**Relevant now**\n{prefetch_context}")
        memory_context = "\n\n".join(memory_parts) if memory_parts else None
        if session_render is not None:
            await deps.memory.record_session_memory_access(
                source="chat_prompt",
                memory=session_memory,
                formatted_chars=len(session_render.text),
                injected_fact_ids=session_render.fact_ids,
                injected_observation_ids=session_render.observation_ids,
                details={"has_context": True},
            )

    skills_context = deps.skill_registry.to_prompt_xml() if deps.skill_registry else None
    learning_context = await get_approved_learning_context(deps.memory) if deps.memory else None
    directives = load_directives()

    notifiers = deps.notifier_service.list_summary() if deps.notifier_service else None

    system_blocks = build_system_blocks(
        source_details={},
        memory_context=memory_context,
        skills_context=skills_context,
        learning_context=learning_context,
        directives=directives,
        notifiers=notifiers,
        use_cache_control=_is_anthropic(deps.chat_model),
    )

    messages = _retain_user_content(messages)

    if not messages:
        messages = [{"role": Role.SYSTEM, "content": system_blocks}]
    elif isinstance(messages[0], dict) and messages[0]["role"] == Role.SYSTEM:
        messages[0]["content"] = system_blocks
    else:
        messages.insert(0, {"role": Role.SYSTEM, "content": system_blocks})

    ctx_blocks = list(context or [])
    if last_activity:
        time_gap = _time_gap_note(last_activity)
        if time_gap:
            ctx_blocks.append(time_gap)

    messages.append({"role": Role.USER, "content": build_user_content(user_message, images, ctx_blocks or None)})

    return messages


async def prepare_chat(
    deps: ChatDeps,
    message: str,
    skip_approvals: bool = False,
    session_id: str | None = None,
    images: list[dict] | None = None,
    context: list[dict] | None = None,
) -> ChatContext:
    registry = deps.run_registry

    if session_id:
        session_data = await deps.session_service.load(session_id)
        if not session_data:
            session_data = SessionData(deps.session_service.create(), [])
    else:
        session_data = await _resolve_session(deps)
    session_state = session_data.state
    session_state.skip_approvals = skip_approvals
    messages = session_data.messages

    user_message = message
    is_init = user_message.strip().lower() == "/init"
    if is_init:
        user_message = INIT_INSTRUCTION
    elif deps.skill_registry:
        user_message, _ = expand_skill_command(user_message, deps.skill_registry)

    name_candidate = message.strip() or ("[image]" if images else "")
    if not session_state.name and not is_init and name_candidate and not name_candidate.startswith("/"):
        session_state.name = name_candidate[:50]

    messages = await _prepare_messages(
        deps, messages, user_message, last_activity=session_state.last_activity, images=images, context=context
    )

    run = registry.create_run(session_state.session_id)
    run.messages = messages

    return ChatContext(
        run=run,
        session_state=session_state,
        is_init=is_init,
        executor=deps.executor,
        tools=deps.executor.get_tools(),
        config=deps.agent_config,
        available_integrations=deps.available_integrations,
        integration_errors=deps.integration_errors,
        session_service=deps.session_service,
        run_registry=deps.run_registry,
        enqueue_run_completed=deps.enqueue_run_completed,
    )


async def submit_chat_message(
    run_registry: RunRegistry,
    build_deps: Callable[[], ChatDeps],
    buses: BusRegistry,
    *,
    message: str,
    session_id: str,
    skip_approvals: bool = False,
    images: list[dict] | None = None,
    context: list[dict] | None = None,
    client_id: str | None = None,
) -> dict[str, str]:
    active_run = run_registry.get_active_run(session_id)
    if active_run:
        entry: dict = {
            "role": Role.USER,
            "content": build_user_content(message, images, context),
        }
        if client_id:
            entry["client_id"] = client_id
        active_run.queue_injection(entry)
        return {"run_id": active_run.run_id, "session_id": session_id}

    deps = build_deps()
    ctx = await prepare_chat(
        deps,
        message,
        skip_approvals,
        session_id=session_id,
        images=images,
        context=context,
    )
    bus = buses.get_or_create(session_id)
    task = asyncio.create_task(run_chat(ctx, bus))
    ctx.run.task = task

    return {"run_id": ctx.run.run_id, "session_id": ctx.session_state.session_id}


async def _drain_backgrounded(
    gen,
    agent: Agent,
    ctx: ChatContext,
    bg_registry,
    tracker: UsageTracker,
) -> None:
    """Continue draining an agent stream silently after the run was backgrounded."""
    read_only = set()
    for t in ctx.tools:
        name = t["function"]["name"]
        tool = ctx.executor.registry.get(name)
        if tool and not tool.mutates:
            read_only.add(name)
    agent.tools = [t for t in agent.tools if t["function"]["name"] in read_only]
    messages = ctx.run.messages
    try:
        async for _ in gen:
            pass
    except asyncio.CancelledError:
        pass
    except Exception:
        _logger.exception("Backgrounded drain failed (run_id=%s)", ctx.run.run_id)
    finally:
        ctx.run.usage = tracker.usage

        save_lock = asyncio.Lock()

        async def _save_snapshot() -> None:
            latest = await ctx.session_service.load(ctx.session_state.session_id)
            current_messages = list(latest.messages) if latest else []
            state = latest.state if latest else ctx.session_state
            await ctx.session_service.save(state, _merge_background_messages(current_messages, messages))

        async def _save_directly(injected: list[dict]) -> None:
            async with save_lock:
                messages.extend(injected)
                try:
                    await _save_snapshot()
                except Exception:
                    _logger.exception("Background direct-save failed (run_id=%s)", ctx.run.run_id)

        bg_registry.on_result = _save_directly

        if injected := ctx.run.drain_injections():
            messages.extend(injected)

        try:
            async with save_lock:
                await _save_snapshot()
        except Exception:
            _logger.exception("Backgrounded final save failed (run_id=%s)", ctx.run.run_id)


async def _emit_ingested_for_client_entries(batch: list[dict], bus: SessionBus, run: RunState) -> None:
    for entry in batch:
        client_id = entry.pop("client_id", None)
        if client_id:
            await bus.emit(MessageIngestedEvent(client_id=client_id, run_id=run.run_id))


def _merge_background_messages(current: list[dict], background: list[dict]) -> list[dict]:
    prefix_len = 0
    for current_msg, background_msg in zip(current, background, strict=False):
        if current_msg != background_msg:
            break
        prefix_len += 1
    return [*current, *background[prefix_len:]]


def _build_get_pending(bus: SessionBus, run: RunState):
    """Closure that drains pending injects and emits message_ingested per client entry."""

    async def _get_pending() -> list[dict]:
        batch = run.drain_injections()
        if not batch:
            return []
        await _emit_ingested_for_client_entries(batch, bus, run)
        return batch

    return _get_pending


async def run_chat(ctx: ChatContext, bus: SessionBus) -> None:
    """Run agent loop, push all events to bus. Fire-and-forget."""
    run = ctx.run
    session_state = ctx.session_state

    run.approval_queue = asyncio.Queue()

    await bus.emit(
        RunStartedEvent(
            session_id=session_state.session_id,
            run_id=run.run_id,
            integrations=ctx.available_integrations,
            integration_errors=ctx.integration_errors,
            skip_approvals=session_state.skip_approvals,
            session_name=session_state.name or "",
        )
    )

    await bus.emit(ThinkingEvent(status="processing..."))
    agent: Agent | None = None
    tracker = UsageTracker()
    result: str | None = None
    try:
        bg_registry = ctx.run_registry.get_background_registry(session_state.session_id)
        io = IOBridge(approval_queue=run.approval_queue, emit=bus.emit)
        agent = create_agent(
            executor=ctx.executor,
            config=ctx.config,
            tools=ctx.tools,
            session_state=session_state,
            run_id=run.run_id,
            io=io,
            extra_auto_approve=INIT_AUTO_APPROVE if ctx.is_init else None,
            background_tasks=bg_registry,
        )
        agent.hooks.on_response = tracker.track

        run.status = RunStatus.RUNNING
        run_finished = False

        agent.hooks.get_pending_messages = _build_get_pending(bus, run)

        async def _on_bg_result(messages: list[dict]) -> None:
            if not run_finished:
                run.queue_injections(messages)

        bg_registry.on_result = _on_bg_result

        result, bg_gen = await run_agent_loop(ctx, agent, bus)

        if bg_gen is not None:
            io.emit = None
            await bus.emit(RunBackgroundedEvent(run_id=run.run_id))
            ctx.run_registry.complete_run(run.run_id)
            run.drain_task = asyncio.create_task(_drain_backgrounded(bg_gen, agent, ctx, bg_registry, tracker))
            return

        if result is None:
            return  # Cancelled

        run.usage = tracker.usage

        if result:
            await bus.emit(TextEvent(content=result))

        usage_dict = run.usage.to_dict()
        usage_dict["cost"] = tracker.cost
        await bus.emit(RunFinishedEvent(run_id=run.run_id, usage=usage_dict))
        ctx.run_registry.complete_run(run.run_id)

    except Exception as e:
        _logger.exception("Chat failed (run_id=%s, session_id=%s)", run.run_id, session_state.session_id)
        await bus.emit(RunErrorEvent(message=str(e), recoverable=False))
        ctx.run_registry.error_run(run.run_id)

    finally:
        if not run.backgrounded:
            pending_messages = run.drain_injections()
            if pending_messages:
                # Emit ingestion events for any client-stamped entries so the
                # frontend queue UI clears, then absorb them into history.
                try:
                    await _emit_ingested_for_client_entries(pending_messages, bus, run)
                except Exception:
                    _logger.exception("Failed to emit message_ingested in finally")
                run.messages.extend(pending_messages)
            run.usage = tracker.usage
            run_finished = True
            last_tokens = getattr(agent, "_last_response", None)
            if last_tokens and last_tokens.usage:
                u = last_tokens.usage
                input_tokens = u.prompt_tokens + u.cache_read_tokens + u.cache_write_tokens
            else:
                input_tokens = None
            metadata = {"last_input_tokens": input_tokens} if input_tokens is not None else None
            await ctx.session_service.save(session_state, run.messages, metadata=metadata)
            event = RunCompleted(
                run_id=run.run_id,
                session_id=session_state.session_id,
                messages=tuple(run.messages),
                usage=run.usage,
                result=result,
            )
            if ctx.enqueue_run_completed:
                await ctx.enqueue_run_completed(event)
