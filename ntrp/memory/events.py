from dataclasses import dataclass


@dataclass
class FactCreated:
    fact_id: int
    text: str


@dataclass
class FactUpdated:
    fact_id: int
    text: str


@dataclass
class FactDeleted:
    fact_id: int


@dataclass
class MemoryCleared:
    pass
