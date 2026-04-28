import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from ntrp.automation.models import Automation
from ntrp.automation.prompts import AUTOMATION_PROMPT, AUTOMATION_SUFFIX
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import CountTrigger, EventTrigger, IdleTrigger, TimeTrigger
from ntrp.constants import (
    SCHEDULER_DEDUP_TTL,
    SCHEDULER_EVENT_MAX_RETRIES,
    SCHEDULER_EVENT_RETRY_BASE_SECONDS,
    SCHEDULER_EVENT_RETRY_MAX_SECONDS,
    SCHEDULER_POLL_INTERVAL,
)
from ntrp.events.internal import RunCompleted
from ntrp.events.sse import AutomationFinishedEvent, AutomationProgressEvent, SSEEvent
from ntrp.events.triggers import EVENT_APPROACHING, EventApproaching, TriggerEvent
from ntrp.logging import get_logger
from ntrp.operator.runner import OperatorDeps, RunRequest, run_agent, run_agent_streaming
from ntrp.server.bus import BusRegistry

AUTOMATION_BUS_KEY = "automation:events"

_logger = get_logger(__name__)


class Scheduler:
    def __init__(self, store: AutomationStore, build_deps: Callable[[], OperatorDeps]):
        self.store = store
        self._build_deps = build_deps
        self._bus_registry: BusRegistry | None = None
        self._task: asyncio.Task | None = None
        self._running: set[asyncio.Task] = set()
        self._handlers: dict[str, Callable[[dict | None], Awaitable[str | None]]] = {}
        self._last_activity_at: datetime = datetime.now(UTC)
        self._started_at: datetime | None = None
        self._last_tick_at: datetime | None = None
        self._last_tick_error: str | None = None
        self._idle_fired: set[str] = set()  # task_ids that already fired this idle period

    def set_bus_registry(self, registry: BusRegistry) -> None:
        self._bus_registry = registry

    def register_handler(self, name: str, handler: Callable[[dict | None], Awaitable[str | None]]) -> None:
        self._handlers[name] = handler

    def update_activity(self) -> None:
        self._last_activity_at = datetime.now(UTC)
        self._idle_fired.clear()  # new activity resets idle state

    def start(self) -> None:
        if self._task is not None:
            return
        self._started_at = datetime.now(UTC)
        self._task = asyncio.create_task(self._startup_and_loop())
        _logger.info("Scheduler started (polling every %ds)", SCHEDULER_POLL_INTERVAL)

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._running:
            for task in self._running:
                task.cancel()
            await asyncio.gather(*self._running, return_exceptions=True)
            self._running.clear()

        _logger.info("Scheduler stopped")

    def _track(self, task: asyncio.Task) -> None:
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def _startup_and_loop(self) -> None:
        try:
            await self._reconcile()
        except Exception:
            _logger.exception("Scheduler reconciliation failed")
        await self._loop()

    async def _reconcile(self) -> None:
        cleared = await self.store.clear_all_running()
        if cleared:
            _logger.info("Cleared %d stale running flags", cleared)
        released = await self.store.release_all_claimed_events()
        if released:
            _logger.info("Released %d stale claimed event rows", released)

        now = datetime.now(UTC)
        for automation in await self.store.list_due(now):
            missed_at = automation.next_run_at
            next_run = self._advance_to_future(automation, now)
            if not next_run:
                continue
            await self.store.set_next_run(automation.task_id, next_run)
            _logger.warning(
                "Missed run of automation %s (was due %s), advanced to %s",
                automation.task_id,
                missed_at.isoformat() if missed_at else "unknown",
                next_run.isoformat(),
            )

        await self._drain_event_backlog()

    @staticmethod
    def _advance_to_future(automation: Automation, now: datetime) -> datetime | None:
        time_triggers = [t for t in automation.triggers if isinstance(t, TimeTrigger)]
        if not time_triggers:
            return None
        trigger = time_triggers[0]
        ref = automation.next_run_at or now
        next_run = trigger.next_run(ref)
        while next_run and next_run <= now:
            next_run = trigger.next_run(next_run)
        return next_run

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
                self._last_tick_at = datetime.now(UTC)
                self._last_tick_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_tick_at = datetime.now(UTC)
                self._last_tick_error = f"{type(exc).__name__}: {exc}"
                _logger.exception("Scheduler tick failed")
            await asyncio.sleep(SCHEDULER_POLL_INTERVAL)

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        due = await self.store.list_due(now)
        for automation in due:
            await self._start_run(automation)
        await self._drain_event_backlog()
        await self._evaluate_idle_triggers(now)

    async def _evaluate_idle_triggers(self, now: datetime) -> None:
        idle_seconds = (now - self._last_activity_at).total_seconds()
        idle_minutes = idle_seconds / 60
        if idle_minutes < 1:
            return

        for auto in await self.store.list_by_trigger_type("idle"):
            if auto.task_id in self._idle_fired:
                continue
            for trigger in auto.triggers:
                if not isinstance(trigger, IdleTrigger):
                    continue
                if idle_minutes < trigger.idle_minutes:
                    continue
                self._idle_fired.add(auto.task_id)
                ctx = {"trigger_type": "idle", "idle_minutes": int(idle_minutes)}
                await self._start_run(auto, context=ctx)
                break

    async def handle_run_completed(self, event: RunCompleted) -> None:
        self.update_activity()
        now = datetime.now(UTC)

        for auto in await self.store.list_by_trigger_type("count"):
            if auto.in_cooldown(now):
                continue
            for trigger in auto.triggers:
                if not isinstance(trigger, CountTrigger):
                    continue
                sid = event.session_id
                count = await self.store.increment_count(auto.task_id, sid, now)
                if count >= trigger.every_n:
                    await self.store.clear_count(auto.task_id, sid)
                    ctx = {
                        "trigger_type": "count",
                        "session_id": event.session_id,
                        "messages": event.messages,
                    }
                    await self._start_run(auto, context=ctx)
                    break

    async def _start_run(self, automation: Automation, context: str | dict | None = None) -> None:
        if automation.in_cooldown(datetime.now(UTC)):
            return
        claimed = await self.store.try_mark_running(automation.task_id, datetime.now(UTC))
        if not claimed:
            _logger.debug("Automation %s already claimed or disabled", automation.task_id)
            return
        execution = asyncio.create_task(self._run_and_finalize(automation, context))
        self._track(execution)

    async def _emit_automation_event(self, event: SSEEvent) -> None:
        if self._bus_registry:
            try:
                bus = self._bus_registry.get_or_create(AUTOMATION_BUS_KEY)
                await bus.emit(event)
            except Exception:
                _logger.debug("Failed to emit automation event", exc_info=True)

    async def _run_and_finalize(
        self,
        automation: Automation,
        context: str | dict | None = None,
        event_queue_id: int | None = None,
        event_attempt_count: int = 0,
    ) -> None:
        await self._emit_automation_event(
            AutomationProgressEvent(task_id=automation.task_id, status="starting..."),
        )
        result: str | None = None
        success = False
        error_message = ""
        try:
            if automation.handler:
                result = await self._run_handler(automation, context)
            else:
                result = await self._run_agent(automation, context)
            success = True
        except Exception as e:
            error_message = f"{type(e).__name__}: {e}"
            _logger.exception("Failed to execute automation %s", automation.task_id)
        finally:
            await self._emit_automation_event(
                AutomationFinishedEvent(task_id=automation.task_id, result=result),
            )
            now = datetime.now(UTC)
            next_run = self._advance_to_future(automation, now)
            await self.store.update_last_run(automation.task_id, now, next_run, result=result)
            if any(t.one_shot for t in automation.triggers):
                await self.store.set_enabled(automation.task_id, False)
            if event_queue_id is not None:
                if success:
                    await self.store.complete_event(event_queue_id)
                else:
                    await self._handle_failed_event(
                        automation.task_id,
                        event_queue_id,
                        event_attempt_count,
                        error_message,
                    )
            await self.store.clear_running(automation.task_id)
            if event_queue_id is not None:
                await self._start_next_queued_event_if_idle(automation.task_id)
            _logger.info("Completed automation %s", automation.task_id)

    async def _run_handler(self, automation: Automation, context: str | dict | None = None) -> str | None:
        handler = self._handlers.get(automation.handler)
        if not handler:
            raise RuntimeError(f"No handler registered for '{automation.handler}'")
        _logger.info("Executing internal automation %s: %s", automation.task_id, automation.description[:80])
        ctx = context if isinstance(context, dict) else (json.loads(context) if context else None)
        return await handler(ctx)

    async def _run_agent(self, automation: Automation, context: str | dict | None = None) -> str | None:
        ctx_str = json.dumps(context) if isinstance(context, dict) else context
        prompt = AUTOMATION_PROMPT.render(description=automation.description, context=ctx_str)

        _logger.info("Executing automation %s: %s", automation.task_id, automation.description[:80])
        request = RunRequest(
            prompt=prompt,
            prompt_suffix=AUTOMATION_SUFFIX,
            writable=automation.writable,
            source_id=automation.task_id,
            model=automation.model,
            skip_approvals=automation.writable,
        )

        if self._bus_registry:
            bus = self._bus_registry.get_or_create(AUTOMATION_BUS_KEY)
            result = await run_agent_streaming(self._build_deps(), request, bus, automation.task_id)
        else:
            result = await run_agent(self._build_deps(), request)

        return result.output

    async def fire_event(self, event: TriggerEvent) -> None:
        now = datetime.now(UTC)
        cutoff = datetime.now(UTC) - timedelta(seconds=SCHEDULER_DEDUP_TTL)
        await self.store.evict_event_claims_older_than(cutoff)
        event_type = event.event_type
        event_key = event.event_key
        context = event.format_context()
        automations = await self.store.list_event_triggered(event_type)
        for automation in automations:
            # Check lead_minutes for event_approaching triggers
            if event_type == EVENT_APPROACHING and isinstance(event, EventApproaching):
                matching_triggers = [
                    t for t in automation.triggers if isinstance(t, EventTrigger) and t.event_type == EVENT_APPROACHING
                ]
                if matching_triggers:
                    trigger = matching_triggers[0]
                    if trigger.lead_minutes is not None and event.minutes_until > int(trigger.lead_minutes):
                        continue

            claimed = await self.store.claim_event(automation.task_id, event_key, now)
            if not claimed:
                continue
            await self.store.enqueue_event(automation.task_id, event_key, context, now)
            _logger.info("Event %s matched automation %s (%s)", event_type, automation.task_id, event_key)
            await self._start_next_queued_event_if_idle(automation.task_id)

    def schedule_run(self, task_id: str) -> None:
        execution = asyncio.create_task(self._manual_run(task_id))
        self._track(execution)

    async def _manual_run(self, task_id: str) -> None:
        if not (automation := await self.store.get(task_id)):
            _logger.warning("Automation %s not found for manual run", task_id)
            return
        if automation.running_since:
            _logger.warning("Automation %s already running, skipping manual run", task_id)
            return
        await self._start_run(automation)

    async def _drain_event_backlog(self) -> None:
        for task_id in await self.store.list_tasks_with_pending_events():
            await self._start_next_queued_event_if_idle(task_id)

    async def _start_next_queued_event_if_idle(self, task_id: str) -> None:
        automation = await self.store.get(task_id)
        if not automation or not automation.enabled:
            return

        now = datetime.now(UTC)
        claimed_running = await self.store.try_mark_running(task_id, now)
        if not claimed_running:
            return

        next_event = await self.store.claim_next_event(task_id, now)
        if next_event is None:
            await self.store.clear_running(task_id)
            return

        queue_id, context, attempt_count = next_event
        execution = asyncio.create_task(
            self._run_and_finalize(
                automation,
                context,
                event_queue_id=queue_id,
                event_attempt_count=attempt_count,
            )
        )
        self._track(execution)

    async def _handle_failed_event(
        self,
        task_id: str,
        queue_id: int,
        attempt_count: int,
        error_message: str,
    ) -> None:
        if attempt_count + 1 >= SCHEDULER_EVENT_MAX_RETRIES:
            await self.store.complete_event(queue_id)
            _logger.error(
                "Dropping queued event %s for automation %s after %d attempts",
                queue_id,
                task_id,
                attempt_count + 1,
            )
            return

        delay = self._retry_delay_seconds(attempt_count)
        next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
        await self.store.fail_event(queue_id, error_message, next_attempt_at)
        _logger.warning(
            "Retrying queued event %s for automation %s in %ds (attempt %d/%d)",
            queue_id,
            task_id,
            delay,
            attempt_count + 1,
            SCHEDULER_EVENT_MAX_RETRIES,
        )

    @staticmethod
    def _retry_delay_seconds(attempt_count: int) -> int:
        backoff = SCHEDULER_EVENT_RETRY_BASE_SECONDS * (2 ** max(attempt_count, 0))
        return min(SCHEDULER_EVENT_RETRY_MAX_SECONDS, backoff)

    async def get_status(self) -> dict:
        now = datetime.now(UTC)
        return {
            "status": "running" if self.is_running else "stopped",
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_tick_error": self._last_tick_error,
            "last_activity_at": self._last_activity_at.isoformat(),
            "running_tasks": len(self._running),
            "registered_handlers": sorted(self._handlers),
            "store": await self.store.get_status(now),
        }
