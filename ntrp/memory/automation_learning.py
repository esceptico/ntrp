from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ntrp.memory.models import LearningEvent

AUTOMATION_RULE_POLICY_VERSION = "learning.automation_rule.v1"
AUTOMATION_RULE_CHANGE_TYPE = "automation_rule"
AUTOMATION_LEARNING_SOURCE_TYPE = "automation_feedback"

_AUTOMATION_SCOPES = frozenset({"automation", "scheduler"})
_MAX_GROUP_EVENTS = 6
_MAX_DETAIL_SIGNALS = 5
_MAX_DIRECT_EVIDENCE_IDS = 20
_REVIEW_OUTCOMES = frozenset({"corrected", "failed", "error", "rejected", "missed"})


@dataclass(frozen=True)
class AutomationRuleProposal:
    scope: str
    signal: str
    evidence_event_ids: tuple[int, ...]
    change_type: str
    target_key: str
    proposal: str
    rationale: str
    expected_metric: str
    details: dict[str, Any]


def build_automation_rule_proposals(events: Iterable[LearningEvent]) -> list[AutomationRuleProposal]:
    grouped: dict[str, list[LearningEvent]] = defaultdict(list)
    for event in events:
        if event.scope not in _AUTOMATION_SCOPES and event.source_type != AUTOMATION_LEARNING_SOURCE_TYPE:
            continue
        if not event.evidence_ids:
            continue
        if event.outcome not in _REVIEW_OUTCOMES:
            continue
        target_key = _target_key(event)
        if len(grouped[target_key]) < _MAX_GROUP_EVENTS:
            grouped[target_key].append(event)

    return [_proposal_for_group(target_key, grouped_events) for target_key, grouped_events in grouped.items()]


def _proposal_for_group(target_key: str, events: list[LearningEvent]) -> AutomationRuleProposal:
    event_ids = tuple(event.id for event in events)
    direct_evidence_ids = _direct_evidence_ids(events)
    signals = [event.signal for event in events[:_MAX_DETAIL_SIGNALS]]
    first = events[0]
    requested_proposal = _detail_text(first, "proposal")
    expected_metric = _detail_text(first, "expected_metric") or "fewer missed, noisy, or failed automation runs"
    outcome_counts = Counter(event.outcome for event in events)

    return AutomationRuleProposal(
        scope="automation",
        signal=f"{len(events)} automation learning event(s) for {target_key}.",
        evidence_event_ids=event_ids,
        change_type=AUTOMATION_RULE_CHANGE_TYPE,
        target_key=target_key,
        proposal=requested_proposal or _default_proposal(first.signal),
        rationale=(
            f"{len(events)} explicit automation feedback event(s) point at {target_key}; "
            f"direct evidence: {', '.join(direct_evidence_ids[:3])}."
        ),
        expected_metric=expected_metric,
        details={
            "source": AUTOMATION_LEARNING_SOURCE_TYPE,
            "event_ids": list(event_ids),
            "direct_evidence_ids": direct_evidence_ids,
            "signals": signals,
            "outcome_counts": dict(outcome_counts),
        },
    )


def _target_key(event: LearningEvent) -> str:
    explicit = _detail_text(event, "target_key")
    if explicit:
        return explicit
    automation_id = _detail_text(event, "automation_id") or _detail_text(event, "task_id") or event.source_id
    if automation_id:
        return f"automation.{automation_id.strip().lower().replace(' ', '_')}"
    return "automation.review"


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


def _default_proposal(signal: str) -> str:
    return f"Review automation scheduling or prompt behavior for: {signal}"
