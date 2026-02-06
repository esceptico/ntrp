import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"  # Waiting for client to execute tool
    WAITING_APPROVAL = "waiting_approval"  # Waiting for user approval
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
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    cancelled: bool = False

    def add_usage(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.updated_at = datetime.now()

    def get_usage(self) -> dict:
        return {
            "prompt": self.prompt_tokens,
            "completion": self.completion_tokens,
            "total": self.prompt_tokens + self.completion_tokens,
        }


class RunRegistry:
    def __init__(self):
        self._runs: dict[str, RunState] = {}
        self._session_runs: dict[str, str] = {}  # session_id -> latest run_id

    def create_run(self, session_id: str) -> RunState:
        run_id = str(uuid4())[:8]
        run = RunState(run_id=run_id, session_id=session_id)
        run.event_queue = asyncio.Queue()
        run.choice_queue = asyncio.Queue()
        self._runs[run_id] = run
        self._session_runs[session_id] = run_id
        return run

    def get_run(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def get_session_run(self, session_id: str) -> RunState | None:
        run_id = self._session_runs.get(session_id)
        if run_id:
            return self._runs.get(run_id)
        return None

    def complete_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run:
            run.status = RunStatus.COMPLETED
            run.updated_at = datetime.now()
        self.cleanup_old_runs()

    def cancel_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run:
            run.cancelled = True
            run.status = RunStatus.CANCELLED
            run.updated_at = datetime.now()

    def cleanup_old_runs(self, max_age_hours: int = 24) -> int:
        now = datetime.now()
        to_remove = []

        for run_id, run in self._runs.items():
            age = (now - run.updated_at).total_seconds() / 3600
            if age > max_age_hours and run.status in (RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.ERROR):
                to_remove.append(run_id)

        for run_id in to_remove:
            run = self._runs.pop(run_id, None)
            if run and self._session_runs.get(run.session_id) == run_id:
                del self._session_runs[run.session_id]

        return len(to_remove)


_registry: RunRegistry | None = None


def get_run_registry() -> RunRegistry:
    global _registry
    if _registry is None:
        _registry = RunRegistry()
    return _registry
