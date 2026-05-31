from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MemoryItemKind = Literal[
    "episode", "observation", "claim", "skill", "proposal", "artifact_ref", "entity", "directory"
]

SelectionRole = Literal["required", "advisory", "evidence_only"]

# Kinds injected into the default prompt surface. Episodes and other raw kinds
# stay evidence-only: reachable via provenance drill-down, never auto-injected.
PROMPT_INJECTED_KINDS: tuple[MemoryItemKind, ...] = ("claim", "skill")

# Raw, low-abstraction kinds that serve as evidence behind claims rather than
# guidance to act on. Everything else is advisory when surfaced.
_EVIDENCE_ONLY_KINDS: frozenset[MemoryItemKind] = frozenset({"episode", "observation", "artifact_ref"})


def selection_role_for_kind(kind: MemoryItemKind) -> SelectionRole:
    return "evidence_only" if kind in _EVIDENCE_ONLY_KINDS else "advisory"


_QUERY_MAX = 10_000


class MemoryActivationRequest(BaseModel):
    query: str = Field(..., min_length=1)
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

    @field_validator("query", mode="before")
    @classmethod
    def _truncate_query(cls, v: object) -> object:
        # A long prompt (e.g. a loop/automation instruction) is a valid retrieval
        # query — truncate it for search instead of crashing activation.
        if isinstance(v, str) and len(v) > _QUERY_MAX:
            return v[:_QUERY_MAX]
        return v


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
    selection_role: SelectionRole = "advisory"
    reason: str = ""


class ExcludedMemoryItem(BaseModel):
    """A memory item surfaced to the model as conflicting or overridden.

    Either a claim that was superseded by a newer one, or a general-scope claim
    that a current-scope claim overrides. Carries the reason so the model can see
    why it is set aside rather than silently dropping it.
    """

    item_id: str
    kind: MemoryItemKind
    content: str
    scope: str
    reason: str
    superseded_by: str | None = None
    overridden_in_scope: str | None = None


class ActivationSkillSuggestion(BaseModel):
    object_id: str = ""
    skill_name: str
    description: str = ""
    score: float = 0.0
    reason: str = ""
    reasons: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    selection_role: SelectionRole = "advisory"
    confidence: float = 0.5


class MemoryActivationBundle(BaseModel):
    query: str
    scope: str | None
    kinds: list[MemoryItemKind] | None
    candidates: list[MemoryActivationCandidate]
    facts_to_trust: list[MemoryActivationCandidate] = Field(default_factory=list)
    skills_to_consider: list[MemoryActivationCandidate] = Field(default_factory=list)
    excluded_or_conflicting: list[ExcludedMemoryItem] = Field(default_factory=list)
    used_chars: int
    prompt_context: str
    usage_event_id: int | None = None
    skills_to_use: list[ActivationSkillSuggestion] = Field(default_factory=list)
