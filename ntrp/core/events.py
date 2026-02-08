from dataclasses import dataclass


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
    result: str
