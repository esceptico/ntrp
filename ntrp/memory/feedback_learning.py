from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ntrp.memory.models import LearningEvent

MEMORY_FEEDBACK_POLICY_VERSION = "learning.memory_feedback.v1"
MEMORY_FEEDBACK_CHANGE_TYPE = "memory_feedback"
MEMORY_FEEDBACK_SOURCE_TYPE = "memory_feedback"

_MAX_GROUP_EVENTS = 8
_MAX_DETAIL_SIGNALS = 5
_MAX_DIRECT_EVIDENCE_IDS = 20
_REVIEW_OUTCOMES = frozenset({"corrected", "deleted", "wrong", "stale", "noisy"})


@dataclass(frozen=True)
class MemoryFeedbackProposal:
    scope: str
    signal: str
    evidence_event_ids: tuple[int, ...]
    change_type: str
    target_key: str
    proposal: str
    rationale: str
    expected_metric: str
    details: dict[str, Any]


@dataclass(frozen=True)
class _FeedbackRule:
    target_key: str
    proposal: str
    expected_metric: str


_RULES: dict[str, _FeedbackRule] = {
    "profile": _FeedbackRule(
        target_key="memory.profile.feedback",
        proposal="Review profile and supersession rules against recent user memory corrections.",
        expected_metric="fewer stale or conflicting profile facts injected into context",
    ),
    "memory_extraction": _FeedbackRule(
        target_key="memory.extraction.feedback",
        proposal="Review extraction and fact classification behavior against recent user fact corrections.",
        expected_metric="fewer manual fact text or metadata corrections",
    ),
    "compression": _FeedbackRule(
        target_key="memory.observations.compression.feedback",
        proposal="Review observation compression behavior against recent user pattern corrections.",
        expected_metric="fewer manual pattern edits",
    ),
    "prune": _FeedbackRule(
        target_key="memory.prune.feedback",
        proposal="Review cleanup rules against memory that users deleted manually.",
        expected_metric="fewer low-value facts and patterns surviving cleanup",
    ),
}


def build_memory_feedback_proposals(events: Iterable[LearningEvent]) -> list[MemoryFeedbackProposal]:
    grouped: dict[str, list[LearningEvent]] = defaultdict(list)
    rules_by_target = {rule.target_key: rule for rule in _RULES.values()}
    scope_by_target = {rule.target_key: scope for scope, rule in _RULES.items()}

    for event in events:
        if event.source_type != MEMORY_FEEDBACK_SOURCE_TYPE:
            continue
        if event.outcome not in _REVIEW_OUTCOMES:
            continue
        if not event.evidence_ids:
            continue
        rule = _RULES.get(event.scope)
        if rule is None:
            continue
        if len(grouped[rule.target_key]) < _MAX_GROUP_EVENTS:
            grouped[rule.target_key].append(event)

    proposals: list[MemoryFeedbackProposal] = []
    for target_key, grouped_events in grouped.items():
        rule = rules_by_target[target_key]
        scope = scope_by_target[target_key]
        proposals.append(_proposal_for_group(scope, rule, grouped_events))
    return proposals


def _proposal_for_group(
    scope: str,
    rule: _FeedbackRule,
    events: list[LearningEvent],
) -> MemoryFeedbackProposal:
    event_ids = tuple(event.id for event in events)
    direct_evidence_ids = _direct_evidence_ids(events)
    outcome_counts = Counter(event.outcome for event in events)
    signals = [event.signal for event in events[:_MAX_DETAIL_SIGNALS]]
    signal = f"{len(events)} direct memory feedback event(s) for {scope}."
    rationale = (
        f"Manual memory feedback is explicit user correction data; "
        f"direct evidence: {', '.join(direct_evidence_ids[:3])}."
    )

    return MemoryFeedbackProposal(
        scope=scope,
        signal=signal,
        evidence_event_ids=event_ids,
        change_type=MEMORY_FEEDBACK_CHANGE_TYPE,
        target_key=rule.target_key,
        proposal=rule.proposal,
        rationale=rationale,
        expected_metric=rule.expected_metric,
        details={
            "source": MEMORY_FEEDBACK_SOURCE_TYPE,
            "event_ids": list(event_ids),
            "direct_evidence_ids": direct_evidence_ids,
            "outcome_counts": dict(outcome_counts),
            "signals": signals,
        },
    )


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
