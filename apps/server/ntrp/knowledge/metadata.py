from ntrp.knowledge.models import KnowledgeObject, KnowledgeObjectType

WRITE_GATE_VERSION = "knowledge.write_gate.v1"
PROMOTION_KIND_SKILL = "skill"
PROMOTION_KIND_LESSON_REVISION = "lesson_revision"
PROMOTION_KIND_MEMORY_WRITE_REVIEW = "memory_write_review"
PROMOTION_KIND_WORKFLOW_CLUSTER_REVIEW = "workflow_cluster_review"
PROCESSOR_CORRECTION_SIGNAL = "correction_signal"
APPROVAL_FLOW_MEMORY_REVIEW_CREATE_SKILL = "memory_review_create_skill"


def is_skill_promotion_candidate(obj: KnowledgeObject) -> bool:
    return obj.object_type == KnowledgeObjectType.ACTION_CANDIDATE and obj.metadata.get("promotion_kind") == PROMOTION_KIND_SKILL


def is_lesson_promotion_candidate(obj: KnowledgeObject) -> bool:
    return obj.object_type == KnowledgeObjectType.PROCEDURE_CANDIDATE or (
        obj.object_type == KnowledgeObjectType.ACTION_CANDIDATE
        and obj.metadata.get("promotion_kind") in {PROMOTION_KIND_LESSON_REVISION, PROMOTION_KIND_MEMORY_WRITE_REVIEW}
    )


def is_correction_candidate(obj: KnowledgeObject) -> bool:
    return (
        obj.object_type == KnowledgeObjectType.ACTION_CANDIDATE
        and (obj.metadata.get("processor") == PROCESSOR_CORRECTION_SIGNAL or obj.metadata.get("kind") == "correction")
    )


def has_write_gate_decision(obj: KnowledgeObject) -> bool:
    return obj.metadata.get("write_gate") == WRITE_GATE_VERSION


def is_workflow_cluster_review_marker(obj: KnowledgeObject) -> bool:
    return obj.object_type == KnowledgeObjectType.ACTION_CANDIDATE and obj.metadata.get("promotion_kind") == PROMOTION_KIND_WORKFLOW_CLUSTER_REVIEW
