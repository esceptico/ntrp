import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ntrp.agent import Agent, Role
from ntrp.constants import CONVERSATION_GAP_THRESHOLD, LOOP_ITERATION_HISTORY_WINDOW
from ntrp.context.models import SessionData, SessionState
from ntrp.core.content import ContextContent, ImageContent, TextContent
from ntrp.core.factory import AgentConfig, create_agent
from ntrp.core.prompts import INIT_INSTRUCTION, build_system_blocks
from ntrp.core.usage_tracker import UsageTracker
from ntrp.events.internal import RunCompleted
from ntrp.events.sse import (
    MessageIngestedEvent,
    RunBackgroundedEvent,
    RunCancelledEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    ThinkingEvent,
)
from ntrp.llm.models import Provider, get_model
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.prefetch import build_memory_prompt_context
from ntrp.notifiers.service import NotifierService
from ntrp.server.bus import BusRegistry, SessionBus
from ntrp.server.state import RunRegistry, RunState, RunStatus
from ntrp.server.stream import run_agent_loop
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.tools.core.context import IOBridge
from ntrp.tools.deferred import build_deferred_tools_prompt_for_schemas
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
    dispatch_session_message: Callable[[str, str, str | None, bool | None], Awaitable[object]] | None = None
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
    dispatch_session_message: Callable[[str, str, str | None, bool | None], Awaitable[object]] | None = None


async def _record_run_started(service: object, run_id: str, session_id: str) -> None:
    fn = getattr(service, "record_chat_run_started", None)
    if fn:
        await fn(run_id, session_id)


def _background_event_recorder(session_service: SessionService):
    async def record(**event) -> None:
        store = session_service.store
        status = str(event.get("status") or "")
        task_id = str(event.get("task_id") or "")
        session_id = str(event.get("session_id") or "")
        if not task_id or not session_id:
            return
        if status == "started":
            await store.record_background_agent_started(
                task_id=task_id,
                session_id=session_id,
                parent_run_id=event.get("parent_run_id"),
                command=str(event.get("command") or ""),
            )
        elif bool(event.get("terminal")):
            await store.record_background_agent_finished(
                task_id=task_id,
                session_id=session_id,
                status=status,
                detail=event.get("detail"),
                result_ref=event.get("result_ref"),
                result_text=event.get("result_text"),
            )
        else:
            await store.record_background_agent_event(
                task_id=task_id,
                session_id=session_id,
                status=status,
                detail=event.get("detail"),
                result_ref=event.get("result_ref"),
            )

    return record


async def _record_run_status(
    service: object,
    run_id: str,
    status: str,
    *,
    stop_reason: str | None = None,
    last_seq: int | None = None,
) -> None:
    fn = getattr(service, "record_chat_run_status", None)
    if fn:
        await fn(run_id, status, stop_reason=stop_reason, last_seq=last_seq)


async def _record_queued_message(
    service: object | None,
    *,
    client_id: str,
    session_id: str,
    run_id: str,
    message: dict,
) -> None:
    fn = getattr(service, "record_chat_queued_message", None)
    if fn:
        await fn(client_id=client_id, session_id=session_id, run_id=run_id, message=message)


async def _mark_queued_message_ingested(service: object | None, client_id: str, *, ingested_seq: int | None) -> None:
    fn = getattr(service, "mark_chat_queued_message_ingested", None)
    if fn:
        await fn(client_id, ingested_seq=ingested_seq)


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
    tools: list[dict],
    last_activity: datetime | None = None,
    images: list[dict] | None = None,
    context: list[dict] | None = None,
    client_id: str | None = None,
) -> list[dict]:
    memory_context = None
    if deps.memory:
        memory_context = await build_memory_prompt_context(
            deps.memory,
            user_message,
            source="chat_prompt",
        )

    skills_context = deps.skill_registry.to_prompt_xml() if deps.skill_registry else None
    directives = load_directives()

    notifiers = deps.notifier_service.list_summary() if deps.notifier_service else None
    deferred_tools_context = (
        build_deferred_tools_prompt_for_schemas(deps.executor.registry, frozenset(deps.executor.tool_services), tools)
        if deps.agent_config.deferred_tools
        else None
    )

    system_blocks = build_system_blocks(
        source_details={},
        memory_context=memory_context,
        skills_context=skills_context,
        directives=directives,
        notifiers=notifiers,
        deferred_tools_context=deferred_tools_context,
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

    user_msg: dict = {
        "role": Role.USER,
        "content": build_user_content(user_message, images, ctx_blocks or None),
    }
    if client_id:
        # Stamp the desktop client's UI id so /session/revert can later
        # match the saved row when the user edits this message.
        user_msg["client_id"] = client_id
        # Loop/background-dispatched messages aren't user input. Tag
        # is_meta so the model sees them but the desktop transcript hides
        # the bubble. Mirrors Claude Code's isMeta convention.
        if client_id.startswith(("loop:", "bg:")):
            user_msg["is_meta"] = True
    messages.append(user_msg)

    return messages


def _persistable_messages(run: RunState) -> list[dict]:
    """The agent view (run.messages) plus any prefix we trimmed off for an
    iteration-mode loop. Disk history must remain complete — the agent
    only sees the tail to keep prompt context bounded."""
    if not run.history_prefix:
        return run.messages
    return [*run.history_prefix, *run.messages]


def _trim_for_loop_iteration(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Cap prior history for an iteration-mode loop fire.

    Returns (prefix_to_persist, view_for_agent). The view keeps the system
    row at index 0 (if present) plus the most recent
    LOOP_ITERATION_HISTORY_WINDOW user/assistant/tool messages; the prefix
    is the middle slice that was dropped from the agent's view but must
    be re-prepended at save time so disk history stays complete.

    The cut respects tool-call boundaries: if the naive WINDOW cut would
    orphan a tool_result (its parent assistant with tool_calls fell into
    the prefix), the cut walks backward until it lands on a clean
    boundary — a user message, or an assistant with no tool_calls.
    Otherwise OpenAI rejects with "No tool call found for function call
    output". The window is therefore a soft target — the tail may grow
    beyond N to keep tool sequences intact.
    """
    if len(messages) <= LOOP_ITERATION_HISTORY_WINDOW:
        return [], messages
    head: list[dict] = []
    rest = messages
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        head = [messages[0]]
        rest = messages[1:]
    if len(rest) <= LOOP_ITERATION_HISTORY_WINDOW:
        return [], messages
    cut = len(rest) - LOOP_ITERATION_HISTORY_WINDOW
    while cut > 0 and not _is_clean_cut_boundary(rest[cut]):
        cut -= 1
    prefix = rest[:cut]
    tail = rest[cut:]
    return prefix, head + tail


def _is_clean_cut_boundary(msg: dict) -> bool:
    """True iff the message can safely be the first kept entry in the
    trimmed tail. Tool results need their parent assistant in scope, and
    an assistant with tool_calls needs its tool results in scope — both
    are unsafe boundaries. A user message or a tool-call-free assistant
    is a clean start.
    """
    role = msg.get("role")
    if role == "user":
        return True
    if role == "assistant" and not msg.get("tool_calls"):
        return True
    return False


async def prepare_chat(
    deps: ChatDeps,
    message: str,
    skip_approvals: bool | None = False,
    session_id: str | None = None,
    images: list[dict] | None = None,
    context: list[dict] | None = None,
    client_id: str | None = None,
    loop_task_id: str | None = None,
) -> ChatContext:
    registry = deps.run_registry

    if session_id:
        session_data = await deps.session_service.load(session_id)
        if not session_data:
            session_data = SessionData(deps.session_service.create(), [])
    else:
        session_data = await _resolve_session(deps)
    session_state = session_data.state
    # None = inherit current session state (used by the loop dispatcher so
    # it doesn't stomp the user's Auto toggle). Explicit bool = set/override.
    if skip_approvals is not None:
        session_state.skip_approvals = skip_approvals
    messages = session_data.messages
    history_prefix: list[dict] = []
    if loop_task_id:
        # Iteration-mode loops would otherwise re-feed the whole prior
        # transcript on every fire. Cap to the last N messages so the
        # prompt context stays bounded for long-running monitors. The
        # dropped head is stashed on the run so save paths can re-prepend
        # it — disk history stays complete even though the agent only
        # sees the tail.
        history_prefix, messages = _trim_for_loop_iteration(messages)

    user_message = message
    is_init = user_message.strip().lower() == "/init"
    if is_init:
        user_message = INIT_INSTRUCTION
    elif deps.skill_registry:
        user_message, _ = expand_skill_command(user_message, deps.skill_registry)

    name_candidate = message.strip() or ("[image]" if images else "")
    if not session_state.name and not is_init and name_candidate and not name_candidate.startswith("/"):
        session_state.name = name_candidate[:50]

    tools = deps.executor.get_tools()
    messages = await _prepare_messages(
        deps,
        messages,
        user_message,
        tools,
        last_activity=session_state.last_activity,
        images=images,
        context=context,
        client_id=client_id,
    )

    run = registry.create_run(session_state.session_id)
    run.messages = messages
    run.session_state = session_state
    run.history_prefix = history_prefix

    return ChatContext(
        run=run,
        session_state=session_state,
        is_init=is_init,
        executor=deps.executor,
        tools=tools,
        config=deps.agent_config,
        available_integrations=deps.available_integrations,
        integration_errors=deps.integration_errors,
        session_service=deps.session_service,
        run_registry=deps.run_registry,
        enqueue_run_completed=deps.enqueue_run_completed,
        dispatch_session_message=deps.dispatch_session_message,
    )


def _loop_task_id_from_client_id(client_id: str | None) -> str | None:
    # Loop dispatcher stamps client_id="loop:<task_id>:<iteration>". The
    # ":" lives inside the task_id (e.g. "loop-shy-otter") so split with
    # maxsplit and rebuild — we want everything between "loop:" and the
    # trailing ":<iteration>" suffix.
    if not client_id or not client_id.startswith("loop:"):
        return None
    rest = client_id[len("loop:") :]
    last_colon = rest.rfind(":")
    if last_colon <= 0:
        return None
    return rest[:last_colon]


async def submit_chat_message(
    run_registry: RunRegistry,
    build_deps: Callable[[], ChatDeps],
    buses: BusRegistry,
    *,
    message: str,
    session_id: str,
    skip_approvals: bool | None = False,
    images: list[dict] | None = None,
    context: list[dict] | None = None,
    client_id: str | None = None,
    session_service: SessionService | None = None,
) -> dict[str, str]:
    loop_task_id = _loop_task_id_from_client_id(client_id)
    is_meta_client = bool(client_id and client_id.startswith(("loop:", "bg:")))

    # Idempotent retry: a POST with a client_id we already accepted within
    # the dedup window returns the same run_id instead of starting a
    # second run or re-queueing the message.
    if client_id:
        existing = run_registry.lookup_otid(session_id, client_id)
        if existing:
            return {"run_id": existing.run_id, "session_id": session_id}

    active_run = run_registry.get_accepting_run(session_id)
    if active_run:
        entry: dict = {
            "role": Role.USER,
            "content": build_user_content(message, images, context),
        }
        if client_id:
            entry["client_id"] = client_id
            if is_meta_client:
                entry["is_meta"] = True
        active_run.queue_injection(entry)
        if client_id:
            await _record_queued_message(
                session_service,
                client_id=client_id,
                session_id=session_id,
                run_id=active_run.run_id,
                message=entry,
            )
        if loop_task_id and not active_run.loop_task_id:
            active_run.loop_task_id = loop_task_id
        if client_id:
            run_registry.register_otid(session_id, client_id, active_run.run_id)
        return {"run_id": active_run.run_id, "session_id": session_id}

    deps = build_deps()
    ctx = await prepare_chat(
        deps,
        message,
        skip_approvals,
        session_id=session_id,
        images=images,
        context=context,
        client_id=client_id,
        loop_task_id=loop_task_id,
    )
    await _record_run_started(deps.session_service, ctx.run.run_id, ctx.session_state.session_id)
    if loop_task_id:
        ctx.run.loop_task_id = loop_task_id
    if is_meta_client:
        ctx.run.is_meta_run = True
    # Persist the user message before the agent starts streaming. Without
    # this the message exists only in `run.messages` (in memory) until the
    # first `on_step_finish` save fires — and a client that switches away
    # and back in that window would lose the message: loadHistory returns
    # the pre-submit history and the SSE replay carries agent events, not
    # the user message itself.
    await deps.session_service.save_progress(ctx.session_state, _persistable_messages(ctx.run))
    bus = buses.get_or_create(session_id)
    task = asyncio.create_task(run_chat(ctx, bus))
    ctx.run.task = task
    _install_cancel_fallback(ctx.run, bus, run_registry, task)
    if client_id:
        run_registry.register_otid(session_id, client_id, ctx.run.run_id)

    return {"run_id": ctx.run.run_id, "session_id": ctx.session_state.session_id}


async def _emit_cancelled_terminal_fallback(run: RunState, bus: SessionBus, run_registry: RunRegistry) -> None:
    if run.cancel_terminal_emitted:
        return
    await bus.emit(RunCancelledEvent(run_id=run.run_id))
    run_registry.finish_cancelled(run.run_id)


def _install_cancel_fallback(
    run: RunState,
    bus: SessionBus,
    run_registry: RunRegistry,
    task: asyncio.Task,
) -> None:
    loop = asyncio.get_running_loop()

    def _on_done(done: asyncio.Task) -> None:
        if not done.cancelled() or run.cancel_terminal_emitted:
            return
        run.cancelled = True
        loop.create_task(_emit_cancelled_terminal_fallback(run, bus, run_registry))

    task.add_done_callback(_on_done)


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
        return
    except Exception:
        _logger.exception("Backgrounded drain failed (run_id=%s)", ctx.run.run_id)
    ctx.run.usage = tracker.usage

    save_lock = asyncio.Lock()

    async def _save_snapshot() -> None:
        latest = await ctx.session_service.load(ctx.session_state.session_id)
        current_messages = list(latest.messages) if latest else []
        state = latest.state if latest else ctx.session_state
        # For iteration-mode loops the agent view is trimmed; prepend the
        # stashed prefix so prefix-matching against disk lines up and the
        # full history is preserved.
        full_view = _persistable_messages(ctx.run)
        await ctx.session_service.save(state, _merge_background_messages(current_messages, full_view))

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
            await _record_run_status(
                ctx.session_service,
                ctx.run.run_id,
                RunStatus.COMPLETED.value,
                last_seq=None,
            )
    except Exception:
        _logger.exception("Backgrounded final save failed (run_id=%s)", ctx.run.run_id)


async def _emit_ingested_for_client_entries(
    batch: list[dict],
    bus: SessionBus,
    run: RunState,
    session_service: SessionService | None = None,
) -> None:
    # Read but do NOT pop — the saved message keeps its client_id so the
    # desktop can later reference it via /session/revert (edit flow) or
    # /sessions/{id}/branch.
    for entry in batch:
        client_id = entry.get("client_id")
        if client_id:
            await bus.emit(MessageIngestedEvent(client_id=client_id, run_id=run.run_id))
            await _mark_queued_message_ingested(session_service, client_id, ingested_seq=bus.next_seq - 1)


def _merge_background_messages(current: list[dict], background: list[dict]) -> list[dict]:
    prefix_len = 0
    for current_msg, background_msg in zip(current, background, strict=False):
        if current_msg != background_msg:
            break
        prefix_len += 1
    return [*current, *background[prefix_len:]]


def _build_get_pending(bus: SessionBus, run: RunState, session_service: SessionService | None = None):
    """Closure that drains pending injects and emits message_ingested per client entry."""

    async def _get_pending() -> list[dict]:
        batch = run.drain_injections()
        if not batch:
            return []
        await _emit_ingested_for_client_entries(batch, bus, run, session_service)
        return batch

    return _get_pending


async def _handle_background_result(
    *,
    run: RunState,
    session_id: str,
    messages: list[dict],
    dispatch_session_message: Callable[[str, str, str | None, bool | None], Awaitable[object]] | None,
    run_finished: bool,
) -> None:
    if not run_finished and not run.cancelled:
        run.queue_injections(messages)
        return
    if not dispatch_session_message:
        return
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str) or not content:
            continue
        client_id = message.get("client_id")
        await dispatch_session_message(
            session_id,
            content,
            client_id if isinstance(client_id, str) else None,
            True,
        )


async def run_chat(ctx: ChatContext, bus: SessionBus) -> None:
    """Run agent loop, push all events to bus. Fire-and-forget."""
    run = ctx.run
    session_state = ctx.session_state
    agent: Agent | None = None
    tracker = UsageTracker()
    result: str | None = None
    run_finished = False

    async def _emit_cancelled_terminal() -> None:
        if run.cancel_terminal_emitted:
            return
        await bus.emit(RunCancelledEvent(run_id=run.run_id))
        ctx.run_registry.finish_cancelled(run.run_id)

    try:
        await bus.emit(
            RunStartedEvent(
                session_id=session_state.session_id,
                run_id=run.run_id,
                integrations=ctx.available_integrations,
                integration_errors=ctx.integration_errors,
                skip_approvals=session_state.skip_approvals,
                session_name=session_state.name or "",
                is_meta_run=bool(run.loop_task_id) or run.is_meta_run,
            )
        )

        await bus.emit(ThinkingEvent(status="processing..."))

        bg_registry = ctx.run_registry.get_background_registry(session_state.session_id)
        bg_registry.record_event = _background_event_recorder(ctx.session_service)
        bg_registry.read_result = lambda task_id: ctx.session_service.store.get_background_agent_result(
            session_state.session_id,
            task_id,
        )
        io = IOBridge(pending_approvals=run.pending_approvals, emit=bus.emit)
        agent = create_agent(
            executor=ctx.executor,
            config=ctx.config,
            tools=ctx.tools,
            session_state=session_state,
            run_id=run.run_id,
            io=io,
            extra_auto_approve=INIT_AUTO_APPROVE if ctx.is_init else None,
            background_tasks=bg_registry,
            loaded_tools=run.loaded_tools,
            loop_task_id=run.loop_task_id,
            parent_tracker=tracker,
        )
        agent.hooks.on_response = tracker.track

        async def _checkpoint(_step: int, _response, messages: list[dict]) -> None:
            # Persist after each agent step so a client navigating back to
            # this session sees the in-flight conversation, not the pre-run
            # snapshot. Lightweight UPDATE, leaves metadata alone — the
            # final save in `finally` re-stamps last_input_tokens.
            #
            # mark_checkpoint advances the bus's "events <= this seq are
            # on disk" watermark. The buffer keeps growing (bounded by
            # RECENT_BUFFER_MAX); a reconnecting client with a cursor at
            # or above this watermark gets a clean buffered replay, while
            # a cursor below it triggers a stream_reset → history reload.
            #
            # `messages` here is the same list object as run.messages — for
            # iteration-mode loops it's the trimmed view, so prepend the
            # stashed prefix to keep disk history complete.
            await ctx.session_service.save_progress(session_state, _persistable_messages(run))
            bus.mark_checkpoint()
            await _record_run_status(
                ctx.session_service,
                run.run_id,
                RunStatus.RUNNING.value,
                last_seq=bus.checkpoint_seq,
            )

        agent.hooks.on_step_finish = _checkpoint

        run.status = RunStatus.RUNNING
        await _record_run_status(ctx.session_service, run.run_id, RunStatus.RUNNING.value)

        agent.hooks.get_pending_messages = _build_get_pending(bus, run, ctx.session_service)

        async def _on_bg_result(messages: list[dict]) -> None:
            await _handle_background_result(
                run=run,
                session_id=session_state.session_id,
                messages=messages,
                dispatch_session_message=ctx.dispatch_session_message,
                run_finished=run_finished,
            )

        bg_registry.on_result = _on_bg_result

        result, bg_gen = await run_agent_loop(ctx, agent, bus)

        if bg_gen is not None:
            io.emit = None
            await bus.emit(RunBackgroundedEvent(run_id=run.run_id))
            await _record_run_status(ctx.session_service, run.run_id, "backgrounded", last_seq=bus.next_seq - 1)
            ctx.run_registry.complete_run(run.run_id)
            run.drain_task = asyncio.create_task(_drain_backgrounded(bg_gen, agent, ctx, bg_registry, tracker))
            return

        if result is None:
            return  # Cancelled

        run.usage = tracker.usage

        # Note: we used to emit a final TextEvent with the cumulative
        # `result` here, which made sense back when the wire had a separate
        # "final text" event (replace-semantics). Under AG-UI the text was
        # already streamed through TEXT_MESSAGE_CONTENT deltas — re-emitting
        # would just duplicate the assistant message in the UI.

        usage_dict = run.usage.to_dict()
        usage_dict["cost"] = tracker.cost
        await bus.emit(
            RunFinishedEvent(
                run_id=run.run_id,
                usage=usage_dict,
                message_count=len(run.messages),
            )
        )
        run_finished = True

    except asyncio.CancelledError:
        run.cancelled = True
        await _emit_cancelled_terminal()
        await _record_run_status(
            ctx.session_service,
            run.run_id,
            RunStatus.CANCELLED.value,
            stop_reason="cancelled",
            last_seq=bus.next_seq - 1,
        )
        return

    except Exception as e:
        _logger.exception("Chat failed (run_id=%s, session_id=%s)", run.run_id, session_state.session_id)
        await bus.emit(RunErrorEvent(run_id=run.run_id, message=str(e), recoverable=False))
        ctx.run_registry.error_run(run.run_id)
        await _record_run_status(
            ctx.session_service,
            run.run_id,
            RunStatus.ERROR.value,
            stop_reason=str(e),
            last_seq=bus.next_seq - 1,
        )

    finally:
        if not run.backgrounded:
            if run.cancelled:
                run.drain_injections()
                run.usage = tracker.usage
                run_finished = True
            else:
                pending_messages = run.drain_injections()
                if pending_messages:
                    # Emit ingestion events for any client-stamped entries so the
                    # frontend queue UI clears, then absorb them into history.
                    try:
                        await _emit_ingested_for_client_entries(pending_messages, bus, run, ctx.session_service)
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
                # `run.messages` is the agent's working-set after this run —
                # for loops that's the trimmed tail (compactor and pricing
                # both operate on this), not the full disk transcript. We
                # persist the working-set size so the next session-open
                # shows the correct message-pressure number on the dial.
                metadata: dict | None = None
                if input_tokens is not None or run.messages:
                    metadata = {}
                    if input_tokens is not None:
                        metadata["last_input_tokens"] = input_tokens
                    metadata["last_message_count"] = len(run.messages)
                await ctx.session_service.save(session_state, _persistable_messages(run), metadata=metadata)
                # Disk now holds the canonical end-of-run state; advance the
                # checkpoint watermark so any cursor below it gets a
                # stream_reset → history reload on reconnect.
                bus.mark_checkpoint()
                await _record_run_status(
                    ctx.session_service,
                    run.run_id,
                    RunStatus.COMPLETED.value,
                    last_seq=bus.next_seq - 1,
                )
                ctx.run_registry.complete_run(run.run_id)
                event = RunCompleted(
                    run_id=run.run_id,
                    session_id=session_state.session_id,
                    messages=tuple(run.messages),
                    usage=run.usage,
                    result=result,
                )
                if ctx.enqueue_run_completed:
                    await ctx.enqueue_run_completed(event)
