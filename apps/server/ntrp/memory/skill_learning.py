import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ntrp.memory.models import LearningEvent

SKILL_NOTE_POLICY_VERSION = "learning.skill_note.v1"
SKILL_NOTE_CHANGE_TYPE = "skill_note"
SKILL_NOTE_SCOPE = "skill"
SKILL_NOTE_SOURCE_TYPE = "skill_learning_event"

_MAX_GROUP_EVENTS = 5
_MAX_DETAIL_SIGNALS = 5
_MAX_DIRECT_EVIDENCE_IDS = 20
_REVIEW_OUTCOMES = frozenset({"corrected", "failed", "error", "rejected"})


@dataclass(frozen=True)
class SkillNoteProposal:
    scope: str
    signal: str
    evidence_event_ids: tuple[int, ...]
    change_type: str
    target_key: str
    proposal: str
    rationale: str
    expected_metric: str
    details: dict[str, Any]


def build_skill_note_proposals(events: Iterable[LearningEvent]) -> list[SkillNoteProposal]:
    grouped: dict[str, list[LearningEvent]] = defaultdict(list)
    for event in events:
        if event.scope != SKILL_NOTE_SCOPE:
            continue
        if not event.evidence_ids:
            continue
        if event.outcome not in _REVIEW_OUTCOMES:
            continue
        target_key = _target_key(event)
        if target_key is None:
            continue
        if len(grouped[target_key]) < _MAX_GROUP_EVENTS:
            grouped[target_key].append(event)

    proposals = [_proposal_for_group(target_key, grouped_events) for target_key, grouped_events in grouped.items()]
    return [proposal for proposal in proposals if proposal is not None]


def _proposal_for_group(target_key: str, events: list[LearningEvent]) -> SkillNoteProposal | None:
    if not events:
        return None

    event_ids = tuple(event.id for event in events)
    direct_evidence_ids = _direct_evidence_ids(events)
    signals = [event.signal for event in events[:_MAX_DETAIL_SIGNALS]]
    first = events[0]
    requested_proposal = _detail_text(first, "proposal")
    skill_name = _detail_text(first, "skill_name") or _detail_text(first, "skill")

    proposal = requested_proposal or _default_proposal(target_key, first.signal)
    rationale = (
        f"{len(events)} explicit skill learning event(s) point at {target_key}; "
        f"direct evidence: {', '.join(direct_evidence_ids[:3])}."
    )
    expected_metric = _detail_text(first, "expected_metric") or "fewer repeated corrections for this workflow"

    return SkillNoteProposal(
        scope=SKILL_NOTE_SCOPE,
        signal=f"{len(events)} skill learning event(s) for {target_key}.",
        evidence_event_ids=event_ids,
        change_type=SKILL_NOTE_CHANGE_TYPE,
        target_key=target_key,
        proposal=proposal,
        rationale=rationale,
        expected_metric=expected_metric,
        details={
            "source": SKILL_NOTE_SOURCE_TYPE,
            "event_ids": list(event_ids),
            "direct_evidence_ids": direct_evidence_ids,
            "signals": signals,
            "skill_name": skill_name,
        },
    )


def _target_key(event: LearningEvent) -> str | None:
    explicit = _detail_text(event, "target_key")
    if explicit:
        return explicit

    skill_name = _detail_text(event, "skill_name") or _detail_text(event, "skill")
    if skill_name:
        return f"skill.{_slug(skill_name)}"

    if event.source_id:
        return f"skill.review.{_slug(event.source_id)}"

    return f"skill.review.event-{event.id}"


def _detail_text(event: LearningEvent, key: str) -> str | None:
    value = event.details.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _direct_evidence_ids(events: list[LearningEvent]) -> list[str]:
    seen: set[str] = set()
    evidence_ids: list[str] = []
    for event in events:
        for evidence_id in event.evidence_ids:
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            evidence_ids.append(evidence_id)
            if len(evidence_ids) >= _MAX_DIRECT_EVIDENCE_IDS:
                return evidence_ids
    return evidence_ids


def _default_proposal(target_key: str, signal: str) -> str:
    return f"Review {target_key} and add a small, procedural note for: {signal}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    return slug[:120] or "unknown"
