from dataclasses import dataclass

from ntrp.agent import Usage

# --- Run lifecycle ---


@dataclass(frozen=True)
class RunCompleted:
    run_id: str
    session_id: str
    messages: tuple[dict, ...]
    usage: Usage
    result: str | None


# --- Memory ---


@dataclass(frozen=True)
class FactUpdated:
    fact_id: int
    text: str


@dataclass(frozen=True)
class FactDeleted:
    fact_id: int


@dataclass(frozen=True)
class MemoryCleared:
    pass
