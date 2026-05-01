import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ntrp.database import deserialize_embedding

type Embedding = np.ndarray


class SourceType(StrEnum):
    CHAT = "chat"
    EXPLICIT = "explicit"

    @classmethod
    def _missing_(cls, value: object) -> "SourceType":
        return cls.EXPLICIT


class FactKind(StrEnum):
    IDENTITY = "identity"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    DECISION = "decision"
    PROJECT = "project"
    EVENT = "event"
    ARTIFACT = "artifact"
    PROCEDURE = "procedure"
    CONSTRAINT = "constraint"
    NOTE = "note"

    @classmethod
    def _missing_(cls, value: object) -> "FactKind":
        return cls.NOTE


class FactLifetime(StrEnum):
    DURABLE = "durable"
    TEMPORARY = "temporary"


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
            if data.get("access_count") is None:
                data["access_count"] = 0
            if data.get("last_accessed_at") is None and data.get("created_at") is not None:
                data["last_accessed_at"] = data["created_at"]
        return data


class Observation(_MemoryModel):
    id: int
    summary: str
    embedding: Embedding | None
    source_fact_ids: list[int]
    history: list[HistoryEntry]
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    access_count: int
    archived_at: datetime | None = None
    created_by: str = "legacy"
    policy_version: str = "legacy"

    @property
    def evidence_count(self) -> int:
        return len(self.source_fact_ids)

    @field_validator("created_at", "updated_at", "last_accessed_at", "archived_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class ProfileEntry(_FrozenModel):
    id: int
    kind: FactKind
    summary: str
    source_fact_ids: list[int] = []
    source_observation_ids: list[int] = []
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    created_by: str = "manual"
    policy_version: str = "manual"
    confidence: float = 1.0

    @field_validator("created_at", "updated_at", "archived_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for name in ("source_fact_ids", "source_observation_ids"):
            raw = data.get(name)
            if isinstance(raw, str):
                data[name] = json.loads(raw) if raw else []
        return data


class Fact(_MemoryModel):
    id: int
    text: str
    embedding: Embedding | None
    source_type: SourceType
    source_ref: str | None
    created_at: datetime
    happened_at: datetime | None
    last_accessed_at: datetime
    access_count: int
    consolidated_at: datetime | None = None
    archived_at: datetime | None = None
    kind: FactKind = FactKind.NOTE
    lifetime: FactLifetime = FactLifetime.DURABLE
    salience: int = 0
    confidence: float = 1.0
    expires_at: datetime | None = None
    pinned_at: datetime | None = None
    superseded_by_fact_id: int | None = None
    entity_refs: list["EntityRef"] = []

    @model_validator(mode="before")
    @classmethod
    def _coerce_lifetime(cls, data: Any) -> Any:
        if isinstance(data, dict):
            legacy_temporary_kind = data.get("kind") == "temporary"
            has_expiry = data.get("expires_at") is not None
            if data.get("lifetime") is None:
                data["lifetime"] = FactLifetime.TEMPORARY.value if has_expiry else FactLifetime.DURABLE.value
            if legacy_temporary_kind:
                data["kind"] = FactKind.NOTE.value
        return data

    @field_validator(
        "created_at",
        "happened_at",
        "last_accessed_at",
        "consolidated_at",
        "archived_at",
        "expires_at",
        "pinned_at",
        mode="before",
    )
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


class MemoryEvent(_FrozenModel):
    id: int
    created_at: datetime
    actor: str
    action: str
    target_type: str
    target_id: int | None = None
    source_type: str | None = None
    source_ref: str | None = None
    reason: str | None = None
    policy_version: str
    details: dict[str, Any] = {}

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_created_at(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)


class MemoryAccessEvent(_FrozenModel):
    id: int
    created_at: datetime
    source: str
    query: str | None = None
    retrieved_fact_ids: list[int] = []
    retrieved_observation_ids: list[int] = []
    injected_fact_ids: list[int] = []
    injected_observation_ids: list[int] = []
    omitted_fact_ids: list[int] = []
    omitted_observation_ids: list[int] = []
    bundled_fact_ids: list[int] = []
    formatted_chars: int = 0
    policy_version: str
    details: dict[str, Any] = {}

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_created_at(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for name in (
            "retrieved_fact_ids",
            "retrieved_observation_ids",
            "injected_fact_ids",
            "injected_observation_ids",
            "omitted_fact_ids",
            "omitted_observation_ids",
            "bundled_fact_ids",
        ):
            raw = data.get(name)
            if isinstance(raw, str):
                data[name] = json.loads(raw)
        details = data.get("details")
        if isinstance(details, str):
            data["details"] = json.loads(details) if details else {}
        return data


class LearningEvent(_FrozenModel):
    id: int
    created_at: datetime
    source_type: str
    source_id: str | None = None
    scope: str
    signal: str
    evidence_ids: list[str] = []
    outcome: str = "unknown"
    details: dict[str, Any] = {}

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_created_at(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        evidence_ids = data.get("evidence_ids")
        if isinstance(evidence_ids, str):
            data["evidence_ids"] = json.loads(evidence_ids) if evidence_ids else []
        details = data.get("details")
        if isinstance(details, str):
            data["details"] = json.loads(details) if details else {}
        return data


class LearningCandidate(_FrozenModel):
    id: int
    created_at: datetime
    updated_at: datetime
    status: str
    change_type: str
    target_key: str
    proposal: str
    rationale: str
    evidence_event_ids: list[int] = []
    expected_metric: str | None = None
    policy_version: str
    applied_at: datetime | None = None
    reverted_at: datetime | None = None
    details: dict[str, Any] = {}

    @field_validator("created_at", "updated_at", "applied_at", "reverted_at", mode="before")
    @classmethod
    def _parse_timestamps(cls, v: Any) -> datetime | None:
        return _parse_datetime(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        evidence_event_ids = data.get("evidence_event_ids")
        if isinstance(evidence_event_ids, str):
            data["evidence_event_ids"] = json.loads(evidence_event_ids) if evidence_event_ids else []
        details = data.get("details")
        if isinstance(details, str):
            data["details"] = json.loads(details) if details else {}
        return data


class FactContext(_FrozenModel):
    facts: list[Fact]
    observations: list[Observation] = []
    bundled_sources: dict[int, list[Fact]] = {}  # observation_id -> source facts
