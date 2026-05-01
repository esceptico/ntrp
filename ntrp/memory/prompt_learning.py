from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ntrp.memory.models import LearningEvent

PROMPT_NOTE_POLICY_VERSION = "learning.prompt_note.v1"
PROMPT_NOTE_CHANGE_TYPE = "prompt_note"

_PROMPT_SCOPES = frozenset({"prompt", "runtime"})
_MAX_GROUP_EVENTS = 6
_MAX_DETAIL_SIGNALS = 5
_MAX_DIRECT_EVIDENCE_IDS = 20
_REVIEW_OUTCOMES = frozenset({"corrected", "failed", "error", "rejected"})


@dataclass(frozen=True)
class PromptNoteProposal:
    scope: str
    signal: str
    evidence_event_ids: tuple[int, ...]
    change_type: str
    target_key: str
    proposal: str
    rationale: str
    expected_metric: str
    details: dict[str, Any]


def build_prompt_note_proposals(events: Iterable[LearningEvent]) -> list[PromptNoteProposal]:
    grouped: dict[str, list[LearningEvent]] = defaultdict(list)
    for event in events:
        if event.scope not in _PROMPT_SCOPES:
            continue
        if not event.evidence_ids:
            continue
        if event.outcome not in _REVIEW_OUTCOMES:
            continue
        target_key = _target_key(event)
        if len(grouped[target_key]) < _MAX_GROUP_EVENTS:
            grouped[target_key].append(event)

    return [_proposal_for_group(target_key, grouped_events) for target_key, grouped_events in grouped.items()]


def _proposal_for_group(target_key: str, events: list[LearningEvent]) -> PromptNoteProposal:
    event_ids = tuple(event.id for event in events)
    direct_evidence_ids = _direct_evidence_ids(events)
    signals = [event.signal for event in events[:_MAX_DETAIL_SIGNALS]]
    first = events[0]
    requested_proposal = _detail_text(first, "proposal")
    expected_metric = _detail_text(first, "expected_metric") or "fewer repeated prompt/runtime corrections"
    scope_counts = Counter(event.scope for event in events)
    outcome_counts = Counter(event.outcome for event in events)

    return PromptNoteProposal(
        scope=first.scope,
        signal=f"{len(events)} prompt/runtime learning event(s) for {target_key}.",
        evidence_event_ids=event_ids,
        change_type=PROMPT_NOTE_CHANGE_TYPE,
        target_key=target_key,
        proposal=requested_proposal or _default_proposal(first.signal),
        rationale=(
            f"{len(events)} explicit prompt/runtime correction event(s) point at {target_key}; "
            f"direct evidence: {', '.join(direct_evidence_ids[:3])}."
        ),
        expected_metric=expected_metric,
        details={
            "source": "prompt_learning_event",
            "event_ids": list(event_ids),
            "direct_evidence_ids": direct_evidence_ids,
            "signals": signals,
            "scope_counts": dict(scope_counts),
            "outcome_counts": dict(outcome_counts),
        },
    )


def _target_key(event: LearningEvent) -> str:
    explicit = _detail_text(event, "target_key")
    if explicit:
        return explicit
    section = _detail_text(event, "prompt_section") or event.scope
    return f"prompt.{section.strip().lower().replace(' ', '_')}"


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
    return f"Add a bounded runtime instruction for this repeated correction: {signal}"
