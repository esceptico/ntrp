from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np

type Embedding = np.ndarray


class FactType(StrEnum):
    WORLD = "world"
    EXPERIENCE = "experience"


class LinkType(StrEnum):
    TEMPORAL = "temporal"
    SEMANTIC = "semantic"
    ENTITY = "entity"


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str


@dataclass
class ExtractedEntityPair:
    source: str
    target: str
    source_type: str = "other"
    target_type: str = "other"


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    entity_pairs: list[ExtractedEntityPair] = field(default_factory=list)


@dataclass
class HistoryEntry:
    previous_text: str
    changed_at: datetime
    reason: str
    source_fact_id: int


@dataclass
class Observation:
    id: int
    summary: str
    embedding: Embedding | None
    evidence_count: int
    source_fact_ids: list[int]
    history: list[HistoryEntry]
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    access_count: int


@dataclass
class Fact:
    id: int
    text: str
    fact_type: FactType
    embedding: Embedding | None
    source_type: str
    source_ref: str | None
    created_at: datetime
    happened_at: datetime | None
    last_accessed_at: datetime
    access_count: int
    consolidated_at: datetime | None = None
    entity_refs: list["EntityRef"] = field(default_factory=list)


@dataclass
class FactLink:
    id: int
    source_fact_id: int
    target_fact_id: int
    link_type: LinkType
    weight: float
    created_at: datetime


@dataclass
class EntityRef:
    id: int
    fact_id: int
    name: str
    entity_type: str
    canonical_id: int | None


@dataclass
class Entity:
    id: int
    name: str
    entity_type: str
    embedding: Embedding | None
    is_core: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class FactContext:
    facts: list[Fact]
    observations: list[Observation] = field(default_factory=list)
