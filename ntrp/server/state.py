import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


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
    prompt_tokens: int = 0
    completion_tokens: int = 0
    event_queue: asyncio.Queue | None = None
    choice_queue: asyncio.Queue | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancelled: bool = False

    def get_usage(self) -> dict:
        return {
            "prompt": self.prompt_tokens,
            "completion": self.completion_tokens,
            "total": self.prompt_tokens + self.completion_tokens,
        }


class RunRegistry:
    def __init__(self):
        self._runs: dict[str, RunState] = {}

    def create_run(self, session_id: str) -> RunState:
        run_id = str(uuid4())[:8]
        run = RunState(run_id=run_id, session_id=session_id)
        self._runs[run_id] = run
        return run

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
            age = (now - run.updated_at).total_seconds() / 3600
            if age > max_age_hours and run.status in (RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.ERROR):
                to_remove.append(run_id)

        for run_id in to_remove:
            self._runs.pop(run_id, None)

        return len(to_remove)


def get_run_registry() -> RunRegistry:
    # RunRegistry lifecycle is managed by Runtime; this is a convenience accessor.
    from ntrp.server.runtime import get_runtime

    return get_runtime().run_registry
