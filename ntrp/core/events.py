from dataclasses import dataclass, field

from ntrp.schedule.models import ScheduledTask


@dataclass(frozen=True)
class ToolExecuted:
    name: str
    duration_ms: int
    depth: int
    is_error: bool
    run_id: str = ""


@dataclass(frozen=True)
class RunStarted:
    run_id: str
    session_id: str


@dataclass(frozen=True)
class RunCompleted:
    run_id: str
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    result: str


@dataclass(frozen=True)
class ConsolidationCompleted:
    facts_processed: int
    observations_created: int


@dataclass(frozen=True)
class IndexingStarted:
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IndexingCompleted:
    updated: int
    deleted: int


@dataclass(frozen=True)
class ScheduleCompleted:
    task: ScheduledTask
    result: str | None


@dataclass(frozen=True)
class ContextCompressed:
    messages: tuple[dict, ...]
    session_id: str
