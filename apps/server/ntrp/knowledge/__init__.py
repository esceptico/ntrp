"""Knowledge-system abstractions over current memory primitives."""

from ntrp.knowledge.models import (
    ActivationBundle,
    ActivationCandidate,
    ActivationRequest,
    ActivationSignal,
    KnowledgeArtifactRenderRequest,
    KnowledgeFeedbackRequest,
    KnowledgeHealthResult,
    KnowledgeNextAction,
    KnowledgeObject,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeProfileSynthesisRequest,
    KnowledgeProfileSynthesisResult,
    KnowledgePruneRequest,
    KnowledgePruneResult,
    KnowledgePublishRequest,
    KnowledgeReflectRequest,
    KnowledgeReflectResult,
    KnowledgeSourceTrace,
    KnowledgeSourceTraceResult,
    KnowledgeSummary,
    KnowledgeSupersessionCommitResult,
    KnowledgeSupersessionProposal,
    KnowledgeSurface,
)


def __getattr__(name: str) -> object:
    if name == "KnowledgeActivationService":
        from ntrp.knowledge.activation import KnowledgeActivationService

        return KnowledgeActivationService
    raise AttributeError(name)


__all__ = [
    "ActivationBundle",
    "ActivationCandidate",
    "ActivationRequest",
    "ActivationSignal",
    "KnowledgeActivationService",
    "KnowledgeNextAction",
    "KnowledgeObject",
    "KnowledgeObjectCreate",
    "KnowledgeProfileSynthesisRequest",
    "KnowledgeProfileSynthesisResult",
    "KnowledgePruneRequest",
    "KnowledgePruneResult",
    "KnowledgeObjectStatus",
    "KnowledgeObjectUpdate",
    "KnowledgeObjectType",
    "KnowledgeArtifactRenderRequest",
    "KnowledgeFeedbackRequest",
    "KnowledgeHealthResult",
    "KnowledgePublishRequest",
    "KnowledgeReflectRequest",
    "KnowledgeReflectResult",
    "KnowledgeSourceTrace",
    "KnowledgeSourceTraceResult",
    "KnowledgeSummary",
    "KnowledgeSupersessionCommitResult",
    "KnowledgeSupersessionProposal",
    "KnowledgeSurface",
]
