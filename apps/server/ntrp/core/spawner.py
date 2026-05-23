import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import isawaitable
from uuid import uuid4

from ntrp.agent import (
    Agent,
    ReasoningBlock,
    ReasoningDelta,
    ReasoningEnded,
    ReasoningStarted,
    Result,
    Role,
    RunBudget,
    ToolCompleted,
    ToolStarted,
)
from ntrp.constants import SUBAGENT_DEFAULT_TIMEOUT
from ntrp.context.models import SessionState
from ntrp.core.compaction_model_request_middleware import CompactionModelRequestMiddleware
from ntrp.core.compactor import Compactor
from ntrp.core.deferred_tools_middleware import DeferredToolsModelRequestMiddleware
from ntrp.core.isolation import IsolationLevel
from ntrp.core.llm_client import llm_client
from ntrp.core.model_context_budget import ToolResultContextBudgetMiddleware
from ntrp.core.tool_executor import NtrpToolExecutor
from ntrp.core.usage_tracker import UsageTracker
from ntrp.events.sse import (
    BackgroundTaskEvent,
    SSEEvent,
    TaskFinishedEvent,
    TaskStartedEvent,
    TokenUsageEvent,
    agent_events_to_sse,
)
from ntrp.llm.models import get_model
from ntrp.logging import get_logger
from ntrp.tools.core.context import IOBridge, RunContext, ToolContext
from ntrp.tools.deferred import append_deferred_tools_prompt, tool_schema_names
from ntrp.tools.executor import ToolExecutor


@dataclass(frozen=True)
class SpawnResult:
    """What `spawn_fn` returns to its caller (research/background tools).

    `text` is the subagent's final message — the only thing that flows into
    the parent's context. `usage` and `cost` describe the subagent's
    internal LLM spend; the calling tool surfaces them via `ToolResult.data`
    so the desktop can render per-agent budget breakdowns without polluting
    the parent's context size with the subagent's internals.

    Background spawns return early (before the subagent has run), so their
    `usage` and `cost` are `None` — the eventual real result is delivered
    via the background-task registry on a separate channel.
    """

    text: str
    usage: dict | None = None
    cost: float | None = None

_logger = get_logger(__name__)

_REASONING_EVENTS = (ReasoningBlock, ReasoningStarted, ReasoningDelta, ReasoningEnded)

# Salvage tunables — used when the inner agent's LLM call fails and we
# try to summarize whatever tool results were gathered before the error.
_SALVAGE_TOOL_CHAR_LIMIT = 4000
_SALVAGE_MAX_TOKENS = 2000
_SALVAGE_TAIL_RESULTS = 20


def get_response_cost(response) -> float:
    try:
        return get_model(response.model).pricing.cost(response.usage)
    except ValueError:
        return 0.0


def _clamp_for_salvage(msg: dict) -> dict:
    """Defensive clamp on tool/assistant content before re-sending to the
    model for the salvage summary — the original failure may have been
    triggered by an oversized tool result, and we don't want to fail the
    salvage pass for the same reason. Handles both plain-string content
    and the list-of-blocks shape that providers use for tool results
    with images or structured payloads."""
    if msg.get("role") not in ("tool", "assistant"):
        return msg
    content = msg.get("content")
    if isinstance(content, str):
        if len(content) <= _SALVAGE_TOOL_CHAR_LIMIT:
            return msg
        head = content[: _SALVAGE_TOOL_CHAR_LIMIT - 60]
        return {**msg, "content": head + "\n\n[clamped for salvage summary]"}
    if isinstance(content, list):
        # Flatten to a string so we never re-emit huge multi-part blocks
        # to the salvage LLM. Crude but safe.
        flat = "\n".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
        if len(flat) <= _SALVAGE_TOOL_CHAR_LIMIT:
            return {**msg, "content": flat}
        head = flat[: _SALVAGE_TOOL_CHAR_LIMIT - 60]
        return {**msg, "content": head + "\n\n[clamped for salvage summary]"}
    return msg


async def _salvage_summary(model: str, child_messages: list[dict], error: str, task: str) -> str:
    """Ask the model to summarize what it found before erroring. Returns
    "" if even this attempt fails (caller falls back to deterministic)."""
    salvage_messages = [_clamp_for_salvage(m) for m in child_messages]
    salvage_messages.append(
        {
            "role": Role.USER,
            "content": (
                f"Your previous step errored: {error}\n\n"
                f"Original task: {task}\n\n"
                "Without making any more tool calls, summarize the partial findings "
                "from the tool results above. Be honest about gaps. The parent agent "
                "will use this as a partial answer, so make every fact recoverable."
            ),
        }
    )
    try:
        response = await llm_client.complete(
            model=model,
            messages=salvage_messages,
            temperature=0.2,
            max_tokens=_SALVAGE_MAX_TOKENS,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        _logger.warning("Salvage summary call failed: %s", e)
        return ""


def _deterministic_salvage(child_messages: list[dict], error: str) -> str:
    """Last-resort fallback when the LLM-based salvage also fails: emit a
    flat list of the tail tool results so the parent at least sees raw
    evidence of what was gathered."""
    tool_results: list[str] = []
    for msg in child_messages:
        if msg.get("role") != "tool":
            continue
        content = (msg.get("content") or "")[:300]
        tool_results.append(f"- {content}")
    body = "\n".join(tool_results[-_SALVAGE_TAIL_RESULTS:])
    return (
        f"[partial — sub-agent errored: {error}]\n"
        f"Last {min(len(tool_results), _SALVAGE_TAIL_RESULTS)} tool results before "
        f"the error:\n{body or '(none)'}"
    )


def _deterministic_cancel_salvage(child_messages: list[dict]) -> str:
    tool_results: list[str] = []
    for msg in child_messages:
        if msg.get("role") not in ("tool", "assistant"):
            continue
        content = (msg.get("content") or "")[:300]
        if content:
            tool_results.append(f"- {content}")
    body = "\n".join(tool_results[-_SALVAGE_TAIL_RESULTS:])
    return (
        "[partial - sub-agent cancelled]\n"
        f"Last {min(len(tool_results), _SALVAGE_TAIL_RESULTS)} findings before "
        f"cancellation:\n{body or '(none)'}"
    )


def _create_session_state(calling_ctx: ToolContext, isolation: IsolationLevel) -> SessionState:
    if isolation == IsolationLevel.SHARED:
        return calling_ctx.session_state

    child_session_id = f"{calling_ctx.session_id}::{uuid4().hex[:8]}"
    return SessionState(
        session_id=child_session_id,
        started_at=datetime.now(UTC),
        auto_approve=calling_ctx.session_state.auto_approve,
        skip_approvals=calling_ctx.session_state.skip_approvals,
    )


def create_spawn_fn(
    executor: ToolExecutor,
    model: str,
    max_depth: int,
    current_depth: int,
    reasoning_effort: str | None = None,
    model_reasoning_efforts: dict[str, str] | None = None,
    compactor: Compactor | None = None,
    max_iterations: int | None = None,
    max_tool_calls: int | None = None,
    max_wall_time_seconds: float | None = None,
    max_cost: float | None = None,
    started_at: float | None = None,
    budget: RunBudget | None = None,
):
    async def spawn_child(
        calling_ctx: ToolContext,
        task: str,
        *,
        system_prompt: str,
        tools: list[dict] | None = None,
        timeout: int = SUBAGENT_DEFAULT_TIMEOUT,
        model_override: str | None = None,
        parent_id: str | None = None,
        isolation: IsolationLevel = IsolationLevel.FULL,
        silent: bool = False,
        background: bool = False,
    ) -> str:
        filtered_tools = tools or executor.get_tools()
        allowed_tool_names = tool_schema_names(filtered_tools)
        child_state = _create_session_state(calling_ctx, isolation)
        child_model = model_override or model
        child_reasoning_effort = (
            model_reasoning_efforts.get(child_model)
            if model_reasoning_efforts is not None
            else reasoning_effort
        )

        child_run = RunContext(
            run_id=calling_ctx.run.run_id,
            current_depth=current_depth + 1,
            max_depth=max_depth,
            max_iterations=max_iterations,
            max_tool_calls=max_tool_calls,
            max_wall_time_seconds=max_wall_time_seconds,
            max_cost=max_cost,
            started_at=calling_ctx.run.started_at if calling_ctx.run.started_at is not None else started_at,
            budget=calling_ctx.run.budget or budget,
            extra_auto_approve=calling_ctx.run.extra_auto_approve,
            research_model=calling_ctx.run.research_model,
            deferred_tools_enabled=calling_ctx.run.deferred_tools_enabled,
            loaded_tools=set(calling_ctx.run.loaded_tools),
            allowed_tool_names=allowed_tool_names,
        )

        if background or silent:
            bg_io = IOBridge()
        else:
            bg_io = calling_ctx.io

        child_ctx = ToolContext(
            session_state=child_state,
            registry=executor.registry,
            run=child_run,
            io=bg_io,
            services=calling_ctx.services,
            ledger=calling_ctx.ledger,
            background_tasks=calling_ctx.background_tasks,
            run_registry=calling_ctx.run_registry,
        )
        child_ctx.spawn_fn = create_spawn_fn(
            executor=executor,
            model=child_model,
            max_depth=max_depth,
            current_depth=current_depth + 1,
            reasoning_effort=child_reasoning_effort,
            model_reasoning_efforts=model_reasoning_efforts,
            compactor=compactor,
            max_iterations=max_iterations,
            max_tool_calls=max_tool_calls,
            max_wall_time_seconds=max_wall_time_seconds,
            max_cost=max_cost,
            started_at=child_run.started_at,
            budget=child_run.budget,
        )

        child_executor = NtrpToolExecutor(executor, child_ctx, ledger=calling_ctx.ledger)
        child_system_prompt = append_deferred_tools_prompt(
            system_prompt,
            executor.registry,
            frozenset(child_ctx.services),
            filtered_tools,
            enabled=child_run.deferred_tools_enabled,
        )

        parent_emit = calling_ctx.io.emit if not silent else None
        lifecycle_task_id = parent_id or f"task-{uuid4().hex[:10]}"
        task_summary = task[:120]
        task_depth = current_depth + 1

        # Sub-agents reuse the parent's compactor so a long-running tool
        # sweep doesn't blow past the model's context window mid-run. The
        # salvage path stays as a backstop, but compaction prevents the
        # underlying failure in the first place.
        middlewares: tuple = (
            DeferredToolsModelRequestMiddleware(
                registry=executor.registry,
                run=child_run,
                get_services=lambda: child_ctx.services,
            ),
            ToolResultContextBudgetMiddleware(),
        )
        compaction_emit = parent_emit if parent_id and not background else None
        compaction_scope = "agent" if compaction_emit else "run"
        if compactor is not None:
            middlewares = (
                *middlewares,
                CompactionModelRequestMiddleware(
                    compactor=compactor,
                    on_compact=child_run.loaded_tools.clear,
                    get_rehydration_state=child_ctx.to_rehydration_state,
                    apply_rehydration_state=child_run.apply_rehydration_state,
                    emit=compaction_emit,
                    run_id=calling_ctx.run.run_id,
                    scope=compaction_scope,
                    parent_tool_call_id=parent_id if compaction_emit else None,
                ),
            )

        sub_tracker = UsageTracker()

        sub_agent = Agent(
            tools=filtered_tools,
            client=llm_client,
            executor=child_executor,
            model=child_model,
            max_iterations=max_iterations,
            max_tool_calls=max_tool_calls,
            max_wall_time_seconds=max_wall_time_seconds,
            max_cost=max_cost,
            max_depth=max_depth,
            current_depth=current_depth + 1,
            parent_id=parent_id,
            reasoning_effort=child_reasoning_effort,
            prompt_cache_key=child_state.session_id,
            model_request_middlewares=middlewares,
            cost_getter=(lambda: calling_ctx.parent_tracker.cost) if calling_ctx.parent_tracker is not None else None,
            started_at=child_run.started_at,
            budget=child_run.budget,
        )

        # Each spawned subagent gets its own UsageTracker so we can attribute
        # its cost (and any nested sub-subagent costs that already rolled up
        # into it) to the caller. After the subagent finishes we roll its
        # `cost` into the parent's tracker — but NOT its `usage`, because the
        # parent's `usage.prompt` is what drives the on-screen "context size"
        # gauge, and the parent's context never actually held the subagent's
        # internal back-and-forth.
        # `hasattr` so test-fake agents without hooks don't trip — they just
        # won't accumulate usage, which is the right behavior for a fake.
        if hasattr(sub_agent, "hooks"):
            sub_agent.hooks.on_response = sub_tracker.track
            if calling_ctx.parent_tracker is not None:

                async def track_parent(response) -> None:
                    await sub_tracker.track(response)
                    cost = get_response_cost(response)
                    calling_ctx.parent_tracker.cost += cost
                    if parent_emit:
                        await parent_emit(
                            TokenUsageEvent(
                                run_id=calling_ctx.run.run_id,
                                usage=response.usage.to_dict(),
                                cost=cost,
                                scope="tool",
                            )
                        )

                sub_agent.hooks.on_response = track_parent
        # Hand sub_tracker down so a nested sub-subagent rolls its cost into
        # *this* subagent's tracker — costs cascade up one level at a time.
        child_ctx.parent_tracker = sub_tracker

        child_messages = [
            {"role": Role.SYSTEM, "content": child_system_prompt},
            {"role": Role.USER, "content": task},
        ]

        def _foreground_child_events(event) -> tuple[SSEEvent, ...]:
            if isinstance(event, _REASONING_EVENTS):
                return ()
            return agent_events_to_sse(event)

        stream_failed = False

        async def _stream_to(to_events) -> str:
            nonlocal stream_failed
            text = ""
            try:
                async for event in sub_agent.stream(child_messages):
                    if isinstance(event, Result):
                        text = event.text
                    elif parent_emit:
                        mapped = to_events(event)
                        if isawaitable(mapped):
                            mapped = await mapped
                        for out in mapped:
                            await parent_emit(out)
                return text
            except asyncio.CancelledError:
                # User-initiated cancel — don't try to salvage, just propagate.
                raise
            except Exception as exc:
                # Fatal LLM/transport error mid-run. Whatever the sub-agent
                # already gathered in `child_messages` is real work we paid
                # for; synthesize a summary instead of returning bare error.
                _logger.warning(
                    "Sub-agent failed mid-run after %d messages, salvaging: %s",
                    len(child_messages),
                    exc,
                )
                stream_failed = True
                summary = await _salvage_summary(child_model, child_messages, str(exc), task)
                if summary:
                    return f"[partial — sub-agent errored: {exc}]\n\n{summary}"
                return _deterministic_salvage(child_messages, str(exc))

        def _settle_with(text: str) -> SpawnResult:
            """Build the final SpawnResult for the caller."""
            return SpawnResult(
                text=text,
                usage=sub_tracker.usage.to_dict(),
                cost=sub_tracker.cost,
            )

        if not background:
            stream_task = asyncio.create_task(_stream_to(_foreground_child_events))
            if calling_ctx.run_registry is not None:
                calling_ctx.run_registry.register_subagent(
                    calling_ctx.run.run_id,
                    lifecycle_task_id,
                    stream_task,
                )
            try:
                if parent_emit:
                    await parent_emit(
                        TaskStartedEvent(
                            run_id=calling_ctx.run.run_id,
                            task_id=lifecycle_task_id,
                            parent_tool_call_id=parent_id,
                            name="Sub-agent",
                            summary=task_summary,
                            depth=task_depth,
                        )
                    )
                text = await asyncio.wait_for(stream_task, timeout=timeout)
                if parent_emit:
                    await parent_emit(
                        TaskFinishedEvent(
                            run_id=calling_ctx.run.run_id,
                            task_id=lifecycle_task_id,
                            parent_tool_call_id=parent_id,
                            status="failed" if stream_failed else "completed",
                            summary="failed" if stream_failed else "completed",
                            depth=task_depth,
                        )
                    )
                return _settle_with(text)
            except asyncio.CancelledError:
                run_state = (
                    calling_ctx.run_registry.get_run(calling_ctx.run.run_id)
                    if calling_ctx.run_registry is not None
                    else None
                )
                handle = run_state.subagents.get(lifecycle_task_id) if run_state else None
                if run_state and not run_state.cancelled and handle and handle.cancel_requested:
                    summary = await _salvage_summary(
                        child_model,
                        child_messages,
                        "cancelled by user",
                        task,
                    )
                    text = (
                        f"[partial - sub-agent cancelled]\n\n{summary}"
                        if summary
                        else _deterministic_cancel_salvage(child_messages)
                    )
                    if parent_emit:
                        await parent_emit(
                            TaskFinishedEvent(
                                run_id=calling_ctx.run.run_id,
                                task_id=lifecycle_task_id,
                                parent_tool_call_id=parent_id,
                                status="cancelled",
                                summary="cancelled",
                                depth=task_depth,
                            )
                        )
                    return _settle_with(text)
                if parent_emit:
                    await parent_emit(
                        TaskFinishedEvent(
                            run_id=calling_ctx.run.run_id,
                            task_id=lifecycle_task_id,
                            parent_tool_call_id=parent_id,
                            status="cancelled",
                            summary="cancelled",
                            depth=task_depth,
                        )
                    )
                raise
            except TimeoutError:
                # Same idea on timeout — try to salvage what we collected.
                if parent_emit:
                    await parent_emit(
                        TaskFinishedEvent(
                            run_id=calling_ctx.run.run_id,
                            task_id=lifecycle_task_id,
                            parent_tool_call_id=parent_id,
                            status="failed",
                            summary=f"timed out after {timeout}s",
                            depth=task_depth,
                        )
                    )
                _logger.warning("Sub-agent timed out after %ss, salvaging", timeout)
                summary = await _salvage_summary(
                    child_model, child_messages, f"timed out after {timeout}s", task
                )
                if summary:
                    return _settle_with(
                        f"[partial — sub-agent timed out after {timeout}s]\n\n{summary}"
                    )
                return _settle_with(
                    _deterministic_salvage(child_messages, f"timed out after {timeout}s")
                )
            finally:
                if calling_ctx.run_registry is not None:
                    calling_ctx.run_registry.finish_subagent(calling_ctx.run.run_id, lifecycle_task_id)
                if not stream_task.done():
                    stream_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await stream_task

        registry = calling_ctx.background_tasks
        task_id = registry.generate_id()
        label = task[:80]

        async def _to_bg_events(event):
            if isinstance(event, ToolStarted):
                detail = event.display_name or event.name
            elif isinstance(event, ToolCompleted):
                detail = f"{event.display_name or event.name}: {event.preview}"
            else:
                return ()
            await registry.record_activity(task_id, detail)
            return (
                BackgroundTaskEvent(
                    task_id=task_id,
                    session_id=registry.session_id,
                    run_id=calling_ctx.run.run_id,
                    command=label,
                    status="activity",
                    detail=detail,
                ),
            )

        async def _run_background():
            try:
                result = await asyncio.wait_for(_stream_to(_to_bg_events), timeout=timeout)
                status = "completed"
            except asyncio.CancelledError:
                result = "Cancelled"
                status = "cancelled"
            except TimeoutError:
                _logger.warning("Background task %s timed out, salvaging", task_id)
                # Belt-and-suspenders: if the salvage call itself raises
                # (e.g. cancelled mid-await), still emit the deterministic
                # fallback so deliver_result always runs.
                try:
                    summary = await _salvage_summary(
                        child_model, child_messages, f"timed out after {timeout}s", task
                    )
                except Exception as salvage_exc:
                    _logger.warning("Background salvage failed: %s", salvage_exc)
                    summary = ""
                result = (
                    f"[partial — background agent timed out after {timeout}s]\n\n{summary}"
                    if summary
                    else _deterministic_salvage(child_messages, f"timed out after {timeout}s")
                )
                status = "failed"
            except Exception as e:
                # _stream_to handles its own salvage internally, so we only
                # land here for exceptions outside the stream loop itself.
                result = f"Error: {e}"
                status = "failed"
                _logger.warning("Background task %s failed: %s", task_id, e)
            try:
                await registry.deliver_result(
                    task_id=task_id,
                    result=result,
                    label=label,
                    status=status,
                    emit=parent_emit,
                )
            except Exception:
                _logger.exception("Background task %s delivery failed", task_id)

        await registry.record_started(task_id=task_id, command=label, parent_run_id=calling_ctx.run.run_id)
        bg_task = asyncio.create_task(_run_background())
        registry.register(task_id, bg_task, command=label)

        if calling_ctx.io.emit:
            await calling_ctx.io.emit(
                BackgroundTaskEvent(
                    task_id=task_id,
                    session_id=registry.session_id,
                    run_id=calling_ctx.run.run_id,
                    command=label,
                    status="started",
                )
            )

        # Background path returns immediately — the real result is delivered
        # asynchronously via registry.deliver_result. Usage/cost belong to
        # the background task's own ledger, not this caller's tool result.
        return SpawnResult(text=f"Background task {task_id} started: {task}")

    return spawn_child
