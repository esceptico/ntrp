"""Workflow-cluster lifecycle helpers for closed-loop skill promotion."""

from __future__ import annotations

from datetime import UTC, datetime

from ntrp.knowledge.models import KnowledgeObject


def parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def workflow_review_marker_is_current(marker: KnowledgeObject, last_seen_at: str | None) -> bool:
    reviewed_at = parse_iso_datetime(marker.metadata.get("workflow_reviewed_at"))
    seen_at = parse_iso_datetime(last_seen_at)
    if reviewed_at is None or seen_at is None:
        return True
    return seen_at <= reviewed_at


def current_workflow_review_markers(markers: list[KnowledgeObject], last_seen_at: str | None) -> list[KnowledgeObject]:
    return [marker for marker in markers if workflow_review_marker_is_current(marker, last_seen_at)]
