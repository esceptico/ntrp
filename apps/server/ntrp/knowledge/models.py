from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class KnowledgeObjectType(StrEnum):
    SOURCE = "source"
    EVIDENCE_REF = "evidence_ref"
    RUN_PROVENANCE = "run_provenance"
    MEMORY_EPISODE = "memory_episode"
    # Legacy name kept for old rows/API compatibility. New code should use
    # MEMORY_EPISODE for true multi-turn episodes, or RUN_PROVENANCE for runs.
    EPISODE = "episode"
    FACT = "fact"
    PATTERN = "pattern"
    LESSON = "lesson"
    PROCEDURE = "procedure"
    ENTITY_PROFILE = "entity_profile"
    PROCEDURE_CANDIDATE = "procedure_candidate"
    ARTIFACT = "artifact"
    ACTION_CANDIDATE = "action_candidate"
    SINK_RECEIPT = "sink_receipt"
    OUTCOME_FEEDBACK = "outcome_feedback"


class KnowledgeObjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class KnowledgeObject(BaseModel):
    id: int
    object_type: KnowledgeObjectType
    title: str
    text: str
    status: KnowledgeObjectStatus
    scope: str | None = None
    activation: str = "prompt"
    proactiveness_level: str = "L0"
    score: float = 0.0
    source_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    reviewed_at: str | None = None
    superseded_by_object_id: int | None = None
    superseded_at: str | None = None
    supersession_reason: str | None = None


class KnowledgeObjectCreate(BaseModel):
    object_type: KnowledgeObjectType
    title: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1, max_length=50_000)
    status: KnowledgeObjectStatus = KnowledgeObjectStatus.DRAFT
    scope: str | None = Field(default=None, max_length=500)
    activation: str = Field(default="prompt", max_length=100)
    proactiveness_level: str = Field(default="L0", max_length=10)
    score: float = 0.0
    source_ids: list[str] = Field(default_factory=list, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryWriteAction(StrEnum):
    WRITE = "write"
    IGNORE = "ignore"
    EXPIRE = "expire"
    REVIEW = "review"


class MemoryWriteDecision(BaseModel):
    action: MemoryWriteAction
    object_type: KnowledgeObjectType | None = None
    target_id: int | None = None
    candidate: KnowledgeObjectCreate | None = None
    patch: dict[str, Any] | None = None
    reason: str
    confidence: float = Field(ge=0, le=1)
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class KnowledgeObjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    text: str | None = Field(default=None, min_length=1, max_length=50_000)
    status: KnowledgeObjectStatus | None = None
    scope: str | None = Field(default=None, max_length=500)
    activation: str | None = Field(default=None, max_length=100)
    proactiveness_level: str | None = Field(default=None, max_length=10)
    score: float | None = None
    source_ids: list[str] | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] | None = None
    superseded_by_object_id: int | None = None
    superseded_at: str | None = None
    supersession_reason: str | None = Field(default=None, max_length=500)


ActivationState = Literal["injected", "selected_not_injected", "omitted"]


class KnowledgeSurface(BaseModel):
    name: str
    object_type: KnowledgeObjectType
    count: int
    description: str
    counts_by_status: dict[KnowledgeObjectStatus, int] = Field(default_factory=dict)


class KnowledgeNextAction(BaseModel):
    title: str
    detail: str
    activation: str = "review"
    proactiveness_level: str = "L2"


class KnowledgeSummary(BaseModel):
    surfaces: list[KnowledgeSurface]
    next_actions: list[KnowledgeNextAction] = Field(default_factory=list)
    policy_version: str = "knowledge.summary.v1"


class KnowledgeReflectRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)


class KnowledgeReflectResult(BaseModel):
    created: list[KnowledgeObject] = Field(default_factory=list)
    skipped: int = 0
    policy_version: str = "knowledge.reflect.v1"


class KnowledgeSkillPromotionResult(BaseModel):
    created: list[KnowledgeObject] = Field(default_factory=list)
    skipped: int = 0
    policy_version: str = "knowledge.skill_promotion.v1"


class KnowledgeWorkflowCluster(BaseModel):
    id: str
    scope: str = "global"
    key: str
    title: str
    summary: str = ""
    trigger_description: str = ""
    status: Literal["candidate", "reviewed", "promoted", "rejected", "stale"] = "candidate"
    promotion_status: Literal["ready", "candidate_exists", "below_threshold"]
    lesson_count: int = 0
    usage_event_count: int = 0
    source_lesson_ids: list[int] = Field(default_factory=list)
    source_episode_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    source_usage_event_ids: list[int] = Field(default_factory=list)
    last_seen_at: str | None = None
    success_count: int = 0
    helpful_count: int = 0
    failure_count: int = 0
    correction_count: int = 0
    has_skill_candidate: bool = False
    skill_candidate_ids: list[int] = Field(default_factory=list)
    why_should_exist: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeWorkflowClusterResult(BaseModel):
    clusters: list[KnowledgeWorkflowCluster] = Field(default_factory=list)
    skipped: int = 0
    policy_version: str = "knowledge.workflow_clusters.v1"


class KnowledgeWorkflowClusterReviewRequest(BaseModel):
    status: Literal["reviewed", "rejected"]
    reason: str | None = Field(default=None, max_length=2_000)


class KnowledgeProfileSynthesisRequest(BaseModel):
    entity_names: list[str] = Field(default_factory=list, max_length=100)
    limit_entities: int = Field(default=25, ge=1, le=200)
    evidence_limit: int = Field(default=20, ge=1, le=100)
    apply: bool = True


class KnowledgeProfileSynthesisResult(BaseModel):
    profiles: list[KnowledgeObject] = Field(default_factory=list)
    skipped: int = 0
    policy_version: str = "knowledge.profiles.trimem.v1"


class KnowledgeArtifactRenderRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    object_ids: list[int] = Field(..., min_length=1, max_length=200)
    scope: str | None = Field(default=None, max_length=500)


class KnowledgePublishRequest(BaseModel):
    artifact_id: int = Field(..., gt=0)
    sink: str = Field(..., min_length=1, max_length=200)
    sink_ref: str | None = Field(default=None, max_length=1_000)


class KnowledgeFeedbackRequest(BaseModel):
    target_object_id: int | None = Field(default=None, gt=0)
    usage_event_id: int | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, max_length=10_000)
    signal: str = Field(..., min_length=1, max_length=100)
    detail: str | None = Field(default=None, max_length=20_000)
    score_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    outcome: (
        Literal["helped", "helpful", "irrelevant", "harmful", "corrected", "task_success", "task_failure", "unknown"]
        | None
    ) = None


class KnowledgeUsageOutcomeRequest(BaseModel):
    target_object_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, max_length=100)
    signal: str = Field(..., min_length=1, max_length=100)
    outcome: Literal["helpful", "helped", "irrelevant", "harmful", "corrected", "task_success", "task_failure", "unknown"]
    detail: str | None = Field(default=None, max_length=20_000)
    user_corrected_answer: bool | None = None


class KnowledgeUsageObjectSummary(BaseModel):
    object_id: int
    object_type: KnowledgeObjectType | None = None
    object_status: KnowledgeObjectStatus | None = None
    object_title: str | None = None
    event_count: int = 0
    retrieved_count: int = 0
    selected_count: int = 0
    injected_count: int = 0
    omitted_count: int = 0
    used_by_model_count: int = 0
    model_visible_count: int = 0
    actually_used_count: int = 0
    selection_reasons: dict[str, int] = Field(default_factory=dict)
    surfaces: dict[str, int] = Field(default_factory=dict)
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    last_activation_rank: int | None = None
    last_activation_score: float | None = None
    last_activation_surface: str | None = None
    last_selection_reason: str | None = None
    last_used_by_model: bool | None = None
    last_activation_state: ActivationState | None = None
    last_model_visible: bool | None = None
    last_actual_use_observed: bool | None = None
    last_activation_reasons: list[str] = Field(default_factory=list)
    last_activation_task: str | None = None
    last_activation_task_id: str | None = None
    last_activation_session_id: str | None = None
    last_activation_run_id: str | None = None
    last_event_id: int | None = None
    last_seen_at: datetime | None = None


class KnowledgeSupersessionProposal(BaseModel):
    superseded_object_id: int = Field(..., gt=0)
    superseding_object_id: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    proposed_by: str = Field(default="model", max_length=100)
    evidence_terms: list[str] = Field(default_factory=list, max_length=50)


class KnowledgeSupersessionCommitResult(BaseModel):
    proposal: KnowledgeSupersessionProposal
    committed: bool
    reason: str
    superseded: KnowledgeObject | None = None
    policy_version: str = "knowledge.supersession.v1"


class KnowledgeFactConsolidationProposal(BaseModel):
    canonical_object_id: int = Field(..., gt=0)
    duplicate_object_ids: list[int] = Field(default_factory=list, min_length=1, max_length=200)
    reason: str = Field(..., min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    proposed_by: str = Field(default="knowledge.fact_consolidation.heuristic.v1", max_length=100)
    evidence_terms: list[str] = Field(default_factory=list, max_length=50)
    source_ids: list[str] = Field(default_factory=list, max_length=500)


class KnowledgeFactConflictProposal(BaseModel):
    object_ids: list[int] = Field(..., min_length=2, max_length=20)
    reason: str = Field(..., min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_terms: list[str] = Field(default_factory=list, max_length=50)
    proposed_by: str = Field(default="knowledge.fact_consolidation.heuristic.v1", max_length=100)


class KnowledgeFactConsolidationResult(BaseModel):
    proposals: list[KnowledgeFactConsolidationProposal] = Field(default_factory=list)
    conflicts: list[KnowledgeFactConflictProposal] = Field(default_factory=list)
    scanned: int = 0
    skipped: int = 0
    policy_version: str = "knowledge.fact_consolidation.v1"


class KnowledgeFactConsolidationCommitRequest(BaseModel):
    proposal: KnowledgeFactConsolidationProposal


class KnowledgeFactConsolidationCommitResult(BaseModel):
    proposal: KnowledgeFactConsolidationProposal
    committed: bool
    reason: str
    commits: list[KnowledgeSupersessionCommitResult] = Field(default_factory=list)
    canonical: KnowledgeObject | None = None
    policy_version: str = "knowledge.fact_consolidation.v1"


class KnowledgePruneRequest(BaseModel):
    older_than_days: int = Field(default=30, ge=1, le=3650)
    limit: int = Field(default=200, ge=1, le=1000)
    apply: bool = False


class KnowledgePruneResult(BaseModel):
    candidates: list[KnowledgeObject] = Field(default_factory=list)
    archived: list[KnowledgeObject] = Field(default_factory=list)
    policy_version: str = "knowledge.retention.v1"


class KnowledgeHealthResult(BaseModel):
    counts: dict[str, int] = Field(default_factory=dict)
    missing_provenance: int = 0
    stale: int = 0
    review_queue: int = 0
    memory_usage_events_7d: int = 0
    memory_helped_7d: int = 0
    memory_irrelevant_7d: int = 0
    memory_harmful_7d: int = 0
    active_legacy_objects: int = 0
    tool_episode_candidates: int = 0
    extracted_without_source_episode: int = 0
    unsourced_active_durable_objects: int = 0
    write_gate_decisions: int = 0
    write_gate_reviews_pending: int = 0
    correction_candidates_pending: int = 0
    skill_candidates_pending: int = 0
    dangling_source_refs: int = 0
    duplicate_fact_clusters: int = 0
    fact_conflict_clusters: int = 0
    policy_version: str = "knowledge.health.v1"


class KnowledgeSourceTrace(BaseModel):
    source_id: str
    object: KnowledgeObject | None = None


class KnowledgeSourceTraceResult(BaseModel):
    object: KnowledgeObject
    sources: list[KnowledgeSourceTrace] = Field(default_factory=list)
    derived_objects: list[KnowledgeObject] = Field(default_factory=list)
    related_objects: list[KnowledgeObject] = Field(default_factory=list)
    superseded_versions: list[KnowledgeObject] = Field(default_factory=list)
    superseded_by_object: KnowledgeObject | None = None
    policy_version: str = "knowledge.sources.v2"
