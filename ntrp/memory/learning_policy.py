from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

LEARNING_POLICY_VERSION = "learning.memory_policy.v1"
LEARNING_POLICY_SOURCE_TYPE = "memory_policy_preview"

_MAX_EVIDENCE_IDS = 20


@dataclass(frozen=True)
class LearningPolicyProposal:
    source_id: str
    scope: str
    signal: str
    evidence_ids: tuple[str, ...]
    change_type: str
    target_key: str
    proposal: str
    rationale: str
    expected_metric: str
    details: dict[str, Any]


def build_memory_policy_proposals(
    *,
    injection_preview: dict[str, Any],
    prune_preview: dict[str, Any],
) -> list[LearningPolicyProposal]:
    proposals: list[LearningPolicyProposal] = []
    proposals.extend(_injection_proposals(injection_preview))
    proposals.extend(_prune_proposals(prune_preview))
    return proposals


def _injection_proposals(preview: dict[str, Any]) -> list[LearningPolicyProposal]:
    candidates = list(preview.get("candidates") or [])
    if not candidates:
        return []

    policy = preview.get("policy") or {}
    summary = preview.get("summary") or {}
    char_budget = int(policy.get("char_budget") or 0)

    reason_counts: Counter[str] = Counter()
    evidence_by_reason: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        access_id = candidate.get("access_event_id")
        if access_id is None:
            continue
        evidence_id = f"memory_access_event:{access_id}"
        for reason in candidate.get("reasons") or []:
            reason_counts[str(reason)] += 1
            if len(evidence_by_reason[str(reason)]) < _MAX_EVIDENCE_IDS:
                evidence_by_reason[str(reason)].append(evidence_id)

    proposals: list[LearningPolicyProposal] = []
    if reason_counts["over_budget"]:
        count = reason_counts["over_budget"]
        proposals.append(
            LearningPolicyProposal(
                source_id="injection:over_budget",
                scope="injection",
                signal=f"{count} recent memory injections exceeded the configured context budget.",
                evidence_ids=tuple(evidence_by_reason["over_budget"]),
                change_type="injection_rule",
                target_key="memory.injection.budget",
                proposal="Review memory injection ranking before increasing the context budget.",
                rationale=f"{count} of {summary.get('events', 0)} recent memory access events exceeded {char_budget} chars.",
                expected_metric="fewer over-budget memory access events",
                details={
                    "reason": "over_budget",
                    "count": count,
                    "char_budget": char_budget,
                    "summary": summary,
                },
            )
        )

    if reason_counts["pattern_heavy"]:
        count = reason_counts["pattern_heavy"]
        proposals.append(
            LearningPolicyProposal(
                source_id="injection:pattern_heavy",
                scope="injection",
                signal=f"{count} recent memory injections were dominated by derived observations.",
                evidence_ids=tuple(evidence_by_reason["pattern_heavy"]),
                change_type="injection_rule",
                target_key="memory.injection.pattern_mix",
                proposal="Review memory ranking so broad observations do not crowd out source facts.",
                rationale="Pattern-heavy injections are useful only when they stay grounded in direct facts.",
                expected_metric="lower share of pattern-heavy injected memory bundles",
                details={
                    "reason": "pattern_heavy",
                    "count": count,
                    "summary": summary,
                },
            )
        )

    if reason_counts["empty_recall"]:
        count = reason_counts["empty_recall"]
        proposals.append(
            LearningPolicyProposal(
                source_id="injection:empty_recall",
                scope="recall",
                signal=f"{count} recent recall tool calls returned no injected memory.",
                evidence_ids=tuple(evidence_by_reason["empty_recall"]),
                change_type="recall_rule",
                target_key="memory.recall.empty_results",
                proposal="Review recall query coverage when user-requested memory lookups return empty results.",
                rationale="Repeated empty recall means either retrieval missed relevant memory or the agent called recall at the wrong time.",
                expected_metric="fewer empty recall tool memory access events",
                details={
                    "reason": "empty_recall",
                    "count": count,
                    "summary": summary,
                },
            )
        )

    return proposals


def _prune_proposals(preview: dict[str, Any]) -> list[LearningPolicyProposal]:
    summary = preview.get("summary") or {}
    total = int(summary.get("total") or 0)
    if total == 0:
        return []

    criteria = preview.get("criteria") or {}
    candidates = list(preview.get("candidates") or [])
    observation_ids = [candidate["id"] for candidate in candidates[:_MAX_EVIDENCE_IDS] if "id" in candidate]

    return [
        LearningPolicyProposal(
            source_id="observations:prune_candidates",
            scope="prune",
            signal=f"{total} stale low-evidence observations are eligible for archival review.",
            evidence_ids=tuple(f"observation:{observation_id}" for observation_id in observation_ids),
            change_type="prune_rule",
            target_key="memory.observations.prune.low_evidence",
            proposal="Review stale low-evidence observations for archival instead of letting them compete in recall.",
            rationale=(
                f"Prune dry-run found {total} observations older than "
                f"{criteria.get('older_than_days')} days with at most {criteria.get('max_sources')} source facts."
            ),
            expected_metric="fewer stale observations competing in recall",
            details={
                "summary": summary,
                "criteria": criteria,
                "observation_ids": observation_ids,
            },
        )
    ]
