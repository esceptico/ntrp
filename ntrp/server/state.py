import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True)
class UsageStats:
    prompt: int
    completion: int
    total: int
    cache_read: int
    cache_write: int
    cost: float


@dataclass
class RunState:
    run_id: str
    session_id: str
    status: RunStatus = RunStatus.PENDING
    messages: list[dict] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float = 0.0
    approval_queue: asyncio.Queue | None = None
    choice_queue: asyncio.Queue | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancelled: bool = False

    def get_usage(self) -> UsageStats:
        return UsageStats(
            prompt=self.prompt_tokens,
            completion=self.completion_tokens,
            total=self.prompt_tokens + self.completion_tokens,
            cache_read=self.cache_read_tokens,
            cache_write=self.cache_write_tokens,
            cost=self.cost,
        )


class RunRegistry:
    def __init__(self):
        self._runs: dict[str, RunState] = {}

    def create_run(self, session_id: str) -> RunState:
        run_id = str(uuid4())[:8]
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
