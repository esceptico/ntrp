import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ntrp.database import deserialize_embedding

type Embedding = np.ndarray


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

    def __repr__(self) -> str:
        fields = []
        for name in type(self).model_fields:
            val = getattr(self, name)
            if isinstance(val, np.ndarray):
                fields.append(f"{name}=<{val.shape}>")
            else:
                fields.append(f"{name}={val!r}")
        return f"{type(self).__name__}({', '.join(fields)})"


class ExtractedEntity(_FrozenModel):
    name: str


class ExtractionResult(_FrozenModel):
    entities: list[ExtractedEntity] = []


class HistoryEntry(_FrozenModel):
    previous_text: str
    changed_at: datetime
    reason: str
    source_fact_id: int
    absorbed_text: str | None = None

    @field_validator("changed_at", mode="before")
    @classmethod
    def _parse_changed_at(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class _MemoryModel(_FrozenModel):
    @field_validator("embedding", mode="before", check_fields=False)
    @classmethod
    def _deserialize_embedding(cls, v: Any) -> Embedding | None:
        if v is None or isinstance(v, np.ndarray):
            return v
        if isinstance(v, bytes):
            return deserialize_embedding(v)
        return v

    @model_validator(mode="before")
    @classmethod
    def _coerce_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("access_count"):
                data["access_count"] = 0
            if data.get("last_accessed_at") is None and data.get("created_at") is not None:
                data["last_accessed_at"] = data["created_at"]
        return data


class Observation(_MemoryModel):
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

    @field_validator("created_at", "updated_at", "last_accessed_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class Fact(_MemoryModel):
    id: int
    text: str
    embedding: Embedding | None
    source_type: str
    source_ref: str | None
    created_at: datetime
    happened_at: datetime | None
    last_accessed_at: datetime
    access_count: int
    consolidated_at: datetime | None = None
    entity_refs: list["EntityRef"] = []

    @field_validator("created_at", "happened_at", "last_accessed_at", "consolidated_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class EntityRef(_FrozenModel):
    id: int
    fact_id: int
    name: str
    entity_id: int | None


class Entity(_FrozenModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class Dream(_FrozenModel):
    id: int
    bridge: str
    insight: str
    source_fact_ids: list[int]
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_source_fact_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = data.get("source_fact_ids")
            if isinstance(raw, str):
                data["source_fact_ids"] = json.loads(raw)
        return data


class FactContext(_FrozenModel):
    facts: list[Fact]
    observations: list[Observation] = []
