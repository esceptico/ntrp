from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MemoryItemKind = Literal[
    "episode", "observation", "claim", "skill", "proposal", "artifact_ref", "entity", "directory"
]


class MemoryActivationRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    scope: str | None = Field(default=None, max_length=500)
    kinds: list[MemoryItemKind] | None = None
    limit: int = Field(default=5, ge=1, le=50)
    task: str | None = Field(default=None, max_length=500)
    task_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    run_id: str | None = Field(default=None, max_length=200)
    surface: Literal["prompt", "context", "tool", "skill"] = "prompt"
    budget_chars: int = Field(default=1_200, ge=200, le=20_000)
    record_access: bool = False


class MemoryActivationCandidate(BaseModel):
    item_id: str
    kind: MemoryItemKind
    content: str
    score: float
    score_breakdown: dict[str, float]
    reasons: list[str] = Field(default_factory=list)
    confidence: float
    scope: str
    tags: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    valid_from: str
    invalid_at: str | None
    created_at: str


class MemoryActivationSelectionTrace(BaseModel):
    rank: int
    item_id: str
    kind: MemoryItemKind
    score: float
    selected: bool
    injected: bool
    reasons: list[str] = Field(default_factory=list)
    chars: int


class ActivationSkillSuggestion(BaseModel):
    object_id: str = ""
    skill_name: str
    description: str = ""
    score: float = 0.0
    reason: str = ""
    reasons: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    selection_role: Literal["required", "advisory", "evidence_only"] = "advisory"
    confidence: float = 0.5


class MemoryActivationBundle(BaseModel):
    query: str
    scope: str | None
    kinds: list[MemoryItemKind] | None
    candidates: list[MemoryActivationCandidate]
    omitted: list[MemoryActivationCandidate] = Field(default_factory=list)
    used_chars: int
    prompt_context: str
    usage_event_id: int | None = None
    skills_to_use: list[ActivationSkillSuggestion] = Field(default_factory=list)
