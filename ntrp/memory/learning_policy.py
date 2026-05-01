from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from ntrp.memory.profile_policy import ProfilePolicyPreview

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
    profile_preview: ProfilePolicyPreview,
    prune_preview: dict[str, Any],
    supersession_candidates: list[dict[str, Any]] | None = None,
) -> list[LearningPolicyProposal]:
    proposals: list[LearningPolicyProposal] = []
    proposals.extend(_injection_proposals(injection_preview))
    proposals.extend(_profile_proposals(profile_preview))
    proposals.extend(_prune_proposals(prune_preview))
    proposals.extend(_supersession_proposals(supersession_candidates or []))
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


def _profile_proposals(preview: ProfilePolicyPreview) -> list[LearningPolicyProposal]:
    proposals: list[LearningPolicyProposal] = []

    if preview.candidates:
        fact_ids = [item.fact.id for item in preview.candidates[:_MAX_EVIDENCE_IDS]]
        proposals.append(
            LearningPolicyProposal(
                source_id="profile:promotion_candidates",
                scope="profile",
                signal=f"{len(preview.candidates)} durable facts look reviewable for always-visible profile memory.",
                evidence_ids=tuple(f"fact:{fact_id}" for fact_id in fact_ids),
                change_type="profile_rule",
                target_key="memory.profile.promotions",
                proposal="Review durable profile candidates and promote only stable identity, preference, relationship, or constraint facts.",
                rationale="Always-visible memory should stay small, direct, and grounded in facts that repeatedly matter.",
                expected_metric="fewer useful facts missed by profile memory without increasing profile noise",
                details={
                    "candidate_count": len(preview.candidates),
                    "policy_version": preview.policy_version,
                    "fact_ids": fact_ids,
                },
            )
        )

    if preview.issues:
        fact_ids = [item.fact.id for item in preview.issues[:_MAX_EVIDENCE_IDS]]
        proposals.append(
            LearningPolicyProposal(
                source_id="profile:quality_issues",
                scope="profile",
                signal=f"{len(preview.issues)} profile facts are overlong or low-confidence.",
                evidence_ids=tuple(f"fact:{fact_id}" for fact_id in fact_ids),
                change_type="profile_rule",
                target_key="memory.profile.quality",
                proposal="Review profile facts that are too long or low-confidence before expanding profile memory.",
                rationale="Profile memory is injected broadly, so weak or bloated entries have a high blast radius.",
                expected_metric="lower profile char count with higher average confidence",
                details={
                    "issue_count": len(preview.issues),
                    "current_chars": preview.current_chars,
                    "char_budget": preview.char_budget,
                    "fact_char_budget": preview.fact_char_budget,
                    "fact_ids": fact_ids,
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


def _supersession_proposals(candidates: list[dict[str, Any]]) -> list[LearningPolicyProposal]:
    if not candidates:
        return []

    pairs = []
    evidence_ids: list[str] = []
    for candidate in candidates[:_MAX_EVIDENCE_IDS]:
        older_id = candidate.get("older_fact_id")
        newer_id = candidate.get("newer_fact_id")
        if older_id is None or newer_id is None:
            continue
        pairs.append(
            {
                "older_fact_id": older_id,
                "newer_fact_id": newer_id,
                "kind": candidate.get("kind"),
                "entity": candidate.get("entity_name"),
            }
        )
        evidence_ids.extend([f"fact:{older_id}", f"fact:{newer_id}"])

    if not pairs:
        return []

    return [
        LearningPolicyProposal(
            source_id="facts:supersession_candidates",
            scope="profile",
            signal=f"{len(pairs)} same-entity profile fact pair(s) may need supersession review.",
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            change_type="supersession_review",
            target_key="memory.facts.supersession.profile",
            proposal="Review older/newer profile fact pairs and mark stale facts as superseded when the newer fact replaces the old one.",
            rationale="Contradictory profile facts should preserve history but avoid competing equally in recall.",
            expected_metric="fewer stale profile facts injected into active context",
            details={
                "pair_count": len(pairs),
                "pairs": pairs,
            },
        )
    ]
