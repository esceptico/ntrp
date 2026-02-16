import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.events import RunCompleted, RunStarted, ScheduleCompleted
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.schedule.models import Recurrence, ScheduledTask, compute_next_run
from ntrp.schedule.store import ScheduleStore
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)

POLL_INTERVAL = 60


@dataclass(frozen=True)
class SchedulerDeps:
    executor: ToolExecutor
    memory: Callable[[], FactMemory | None]
    model: str
    max_depth: int
    channel: Channel
    source_details: Callable[[], dict[str, dict]]
    create_session: Callable[[], SessionState]
    explore_model: str | None = None


class Scheduler:
    def __init__(self, deps: SchedulerDeps, store: ScheduleStore):
        self.deps = deps
        self.store = store
        self._task: asyncio.Task | None = None
        self._running_execution: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        _logger.info("Scheduler started (polling every %ds)", POLL_INTERVAL)

    @property
    def is_running(self) -> bool:
        return self._task is not None

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._running_execution and not self._running_execution.done():
            try:
                await asyncio.wait_for(self._running_execution, timeout=30)
            except (TimeoutError, asyncio.CancelledError):
                self._running_execution.cancel()
            self._running_execution = None

        _logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("Scheduler tick failed")
            await asyncio.sleep(POLL_INTERVAL)

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        due_tasks = await self.store.list_due(now)
        for task in due_tasks:
            await self.store.mark_running(task.task_id, now)
            execution = asyncio.create_task(self._run_and_finalize(task))
            self._running_execution = execution
            try:
                await asyncio.shield(execution)
            except asyncio.CancelledError:
                return  # Loop cancelled, but execution continues — stop() will await it
            finally:
                self._running_execution = None

    async def _run_and_finalize(self, task: ScheduledTask) -> None:
        try:
            await self._execute_task(task)
        except Exception:
            _logger.exception("Failed to execute scheduled task %s", task.task_id)
        finally:
            await self.store.clear_running(task.task_id)

    async def _run_agent(self, task: ScheduledTask) -> str | None:
        # Delayed imports: scheduler → agent → tools creates a circular import chain
        from ntrp.core.agent import Agent
        from ntrp.core.prompts import build_system_prompt, scheduled_task_suffix
        from ntrp.core.spawner import create_spawn_fn
        from ntrp.memory.formatting import format_session_memory
        from ntrp.tools.core.context import IOBridge, RunContext, ToolContext
        from ntrp.tools.directives import load_directives

        _logger.info("Executing scheduled task %s: %s", task.task_id, task.description[:80])

        run_id = str(uuid4())[:8]
        memory = self.deps.memory()
        memory_context = None
        if memory:
            user_facts = await memory.get_context()
            memory_context = format_session_memory(user_facts=user_facts) or None

        system_prompt = build_system_prompt(
            source_details=self.deps.source_details(),
            memory_context=memory_context,
            directives=load_directives(),
        )
        system_prompt += scheduled_task_suffix(bool(task.notifiers))

        session_state = self.deps.create_session()

        tool_ctx = ToolContext(
            session_state=session_state,
            registry=self.deps.executor.registry,
            run=RunContext(
                run_id=run_id,
                max_depth=self.deps.max_depth,
                explore_model=self.deps.explore_model,
            ),
            io=IOBridge(),
            memory=memory,
            channel=self.deps.channel,
        )
        tool_ctx.spawn_fn = create_spawn_fn(
            executor=self.deps.executor,
            model=self.deps.model,
            max_depth=self.deps.max_depth,
            current_depth=0,
            cancel_check=None,
        )

        tools = self.deps.executor.get_tools() if task.writable else self.deps.executor.get_tools(mutates=False)
        agent = Agent(
            tools=tools,
            tool_executor=self.deps.executor,
            model=self.deps.model,
            system_prompt=system_prompt,
            ctx=tool_ctx,
            max_depth=self.deps.max_depth,
            current_depth=0,
        )

        self.deps.channel.publish(RunStarted(run_id=run_id, session_id=session_state.session_id))
        result: str | None = None
        try:
            result = await agent.run(task.description)
        finally:
            self.deps.channel.publish(
                RunCompleted(
                    run_id=run_id,
                    prompt_tokens=agent.total_input_tokens,
                    completion_tokens=agent.total_output_tokens,
                    result=result or "",
                )
            )

        self.deps.channel.publish(ScheduleCompleted(task=task, result=result))

        return result

    async def _execute_task(self, task: ScheduledTask) -> None:
        result = await self._run_agent(task)
        now = datetime.now(UTC)
        if task.recurrence == Recurrence.ONCE:
            await self.store.update_last_run(task.task_id, now, now, result=result)
            await self.store.set_enabled(task.task_id, False)
        else:
            next_run = compute_next_run(task.time_of_day, task.recurrence, after=now)
            await self.store.update_last_run(task.task_id, now, next_run, result=result)
        _logger.info("Completed scheduled task %s", task.task_id)

    async def run_now(self, task_id: str) -> str | None:
        task = await self.store.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task.running_since:
            raise ValueError(f"Task {task_id} is already running")

        await self.store.mark_running(task.task_id, datetime.now(UTC))
        try:
            result = await self._run_agent(task)
            now = datetime.now(UTC)
            if task.recurrence == Recurrence.ONCE:
                await self.store.update_last_run(task.task_id, now, task.next_run_at, result=result)
            else:
                next_run = compute_next_run(task.time_of_day, task.recurrence, after=now)
                await self.store.update_last_run(task.task_id, now, next_run, result=result)
            return result
        finally:
            await self.store.clear_running(task.task_id)
