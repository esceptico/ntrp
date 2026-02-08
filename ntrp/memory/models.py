from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ntrp.database import deserialize_embedding

type Embedding = np.ndarray


class FactType(StrEnum):
    WORLD = "world"
    EXPERIENCE = "experience"


class LinkType(StrEnum):
    TEMPORAL = "temporal"
    SEMANTIC = "semantic"
    ENTITY = "entity"


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise ValueError(f"Cannot parse datetime from {type(value)}")


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class ExtractedEntity(_FrozenModel):
    name: str
    entity_type: str


class ExtractedEntityPair(_FrozenModel):
    source: str
    target: str
    source_type: str = "other"
    target_type: str = "other"


class ExtractionResult(_FrozenModel):
    entities: list[ExtractedEntity] = []
    entity_pairs: list[ExtractedEntityPair] = []


class HistoryEntry(_FrozenModel):
    previous_text: str
    changed_at: datetime
    reason: str
    source_fact_id: int

    @field_validator("changed_at", mode="before")
    @classmethod
    def _parse_changed_at(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class Observation(_FrozenModel):
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

    @field_validator("embedding", mode="before")
    @classmethod
    def _deserialize_embedding(cls, v: Any) -> Embedding | None:
        if v is None or isinstance(v, np.ndarray):
            return v
        if isinstance(v, bytes):
            return deserialize_embedding(v)
        return v

    @field_validator("created_at", "updated_at", "last_accessed_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_access_count(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("access_count"):
                data["access_count"] = 0
            # Fallback: last_accessed_at defaults to created_at
            if data.get("last_accessed_at") is None and data.get("created_at") is not None:
                data["last_accessed_at"] = data["created_at"]
        return data


class Fact(_FrozenModel):
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
    entity_refs: list["EntityRef"] = []

    @field_validator("fact_type", mode="before")
    @classmethod
    def _coerce_fact_type(cls, v: Any) -> FactType:
        return FactType(v) if isinstance(v, str) else v

    @field_validator("embedding", mode="before")
    @classmethod
    def _deserialize_embedding(cls, v: Any) -> Embedding | None:
        if v is None or isinstance(v, np.ndarray):
            return v
        if isinstance(v, bytes):
            return deserialize_embedding(v)
        return v

    @field_validator("created_at", "happened_at", "last_accessed_at", "consolidated_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("access_count"):
                data["access_count"] = 0
            if data.get("last_accessed_at") is None and data.get("created_at") is not None:
                data["last_accessed_at"] = data["created_at"]
        return data


class FactLink(_FrozenModel):
    id: int
    source_fact_id: int
    target_fact_id: int
    link_type: LinkType
    weight: float
    created_at: datetime

    @field_validator("link_type", mode="before")
    @classmethod
    def _coerce_link_type(cls, v: Any) -> LinkType:
        return LinkType(v) if isinstance(v, str) else v

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class EntityRef(_FrozenModel):
    id: int
    fact_id: int
    name: str
    entity_type: str
    canonical_id: int | None


class Entity(_FrozenModel):
    id: int
    name: str
    entity_type: str
    embedding: Embedding | None
    is_core: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("embedding", mode="before")
    @classmethod
    def _deserialize_embedding(cls, v: Any) -> Embedding | None:
        if v is None or isinstance(v, np.ndarray):
            return v
        if isinstance(v, bytes):
            return deserialize_embedding(v)
        return v

    @field_validator("is_core", mode="before")
    @classmethod
    def _coerce_bool(cls, v: Any) -> bool:
        return bool(v)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class FactContext(_FrozenModel):
    facts: list[Fact]
    observations: list[Observation] = []
