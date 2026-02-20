import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from ntrp.usage import Usage


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
    approval_queue: asyncio.Queue | None = None
    choice_queue: asyncio.Queue | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancelled: bool = False


class RunRegistry:
    def __init__(self):
        self._runs: dict[str, RunState] = {}

    def create_run(self, session_id: str) -> RunState:
        run_id = secrets.token_hex(4)
        run = RunState(run_id=run_id, session_id=session_id)
        self._runs[run_id] = run
        return run

    @property
    def active_run_count(self) -> int:
        return sum(1 for r in self._runs.values() if r.status == RunStatus.RUNNING)

    def get_run(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def complete_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run:
            run.status = RunStatus.COMPLETED
            run.updated_at = datetime.now(UTC)
        self.cleanup_old_runs()

    def cancel_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run:
            run.cancelled = True
            run.status = RunStatus.CANCELLED
            run.updated_at = datetime.now(UTC)

    def cleanup_old_runs(self, max_age_hours: int = 24) -> int:
        now = datetime.now(UTC)
        to_remove = []

        for run_id, run in self._runs.items():
            age = (now - run.updated_at) / timedelta(hours=1)
            if age > max_age_hours and run.status in (RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.ERROR):
                to_remove.append(run_id)

        for run_id in to_remove:
            self._runs.pop(run_id, None)

        return len(to_remove)
