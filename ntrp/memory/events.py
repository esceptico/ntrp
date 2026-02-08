from dataclasses import dataclass


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
