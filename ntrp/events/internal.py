from dataclasses import dataclass, field

from ntrp.usage import Usage

# --- Run lifecycle ---


@dataclass(frozen=True)
class RunStarted:
    run_id: str
    session_id: str


@dataclass(frozen=True)
class RunCompleted:
    run_id: str
    usage: Usage
    result: str | None


@dataclass(frozen=True)
class ToolExecuted:
    name: str
    duration_ms: int
    depth: int
    is_error: bool
    run_id: str


@dataclass(frozen=True)
class ContextCompressed:
    messages: tuple[dict, ...]
    session_id: str


# --- Memory ---


@dataclass(frozen=True)
class FactCreated:
    fact_id: int
    text: str


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


@dataclass(frozen=True)
class ConsolidationCompleted:
    facts_processed: int
    observations_created: int


# --- Indexing ---


@dataclass(frozen=True)
class IndexingStarted:
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IndexingCompleted:
    updated: int
    deleted: int


# --- Sources ---


@dataclass(frozen=True)
class SourceChanged:
    source_name: str
