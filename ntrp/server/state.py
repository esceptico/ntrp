import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from coolname import generate_slug

from ntrp.agent import Usage
from ntrp.tools.core.context import BackgroundTaskRegistry


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class RunState:
    run_id: str
    session_id: str
    status: RunStatus = RunStatus.PENDING
    messages: list[dict] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    approval_queue: asyncio.Queue[dict] | None = None
    task: asyncio.Task | None = None
    inject_queue: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancelled: bool = False
    backgrounded: bool = False
    drain_task: asyncio.Task | None = None


class RunRegistry:
    def __init__(self):
        self._runs: dict[str, RunState] = {}
        self._active_by_session: dict[str, str] = {}
        self._bg_registries: dict[str, BackgroundTaskRegistry] = {}

    def get_background_registry(self, session_id: str) -> BackgroundTaskRegistry:
        if session_id not in self._bg_registries:
            self._bg_registries[session_id] = BackgroundTaskRegistry(session_id=session_id)
        return self._bg_registries[session_id]

    def create_run(self, session_id: str) -> RunState:
        run_id = generate_slug(2)
        run = RunState(run_id=run_id, session_id=session_id)
        self._runs[run_id] = run
        self._active_by_session[session_id] = run_id
        return run

    @property
    def active_run_count(self) -> int:
        return len(self._active_by_session)

    def get_run(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def get_active_run(self, session_id: str) -> RunState | None:
        run_id = self._active_by_session.get(session_id)
        if not run_id:
            return None
        run = self._runs.get(run_id)
        if run and run.status == RunStatus.RUNNING:
            return run
        self._active_by_session.pop(session_id, None)
        return None

    def complete_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run:
            run.status = RunStatus.COMPLETED
            run.updated_at = datetime.now(UTC)
            self._active_by_session.pop(run.session_id, None)
        self.cleanup_old_runs()

    def cancel_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run:
            run.cancelled = True
            run.status = RunStatus.CANCELLED
            run.updated_at = datetime.now(UTC)
            self._active_by_session.pop(run.session_id, None)
            if run.task and not run.task.done():
                run.task.cancel()
        self.cleanup_old_runs()

    async def cancel_all(self, timeout: float = 5.0) -> int:
        tasks = []
        for run in self._runs.values():
            if run.status == RunStatus.RUNNING and run.task and not run.task.done():
                run.cancelled = True
                run.status = RunStatus.CANCELLED
                run.task.cancel()
                tasks.append(run.task)
            if run.drain_task and not run.drain_task.done():
                run.drain_task.cancel()
                tasks.append(run.drain_task)
        self._active_by_session.clear()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)
        return len(tasks)

    def error_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run:
            run.status = RunStatus.ERROR
            run.updated_at = datetime.now(UTC)
            self._active_by_session.pop(run.session_id, None)
        self.cleanup_old_runs()

    def cleanup_old_runs(self, max_age_hours: int = 24) -> int:
        now = datetime.now(UTC)
        to_remove = []

        for run_id, run in self._runs.items():
            age = (now - run.updated_at) / timedelta(hours=1)
            if age > max_age_hours and run.status in (RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.ERROR):
                to_remove.append(run_id)

        removed_sessions: set[str] = set()
        for run_id in to_remove:
            run = self._runs.pop(run_id, None)
            if run:
                removed_sessions.add(run.session_id)

        for session_id in removed_sessions:
            has_runs = any(r.session_id == session_id for r in self._runs.values())
            if not has_runs:
                self._bg_registries.pop(session_id, None)

        return len(to_remove)
