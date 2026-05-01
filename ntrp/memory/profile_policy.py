from dataclasses import dataclass
from typing import Literal

from ntrp.memory.models import Fact

DEFAULT_PROFILE_CHAR_BUDGET = 1200
DEFAULT_PROFILE_FACT_CHAR_BUDGET = 220
DEFAULT_PROFILE_REVIEW_ACCESS_COUNT = 3
PROFILE_POLICY_VERSION = "memory.profile.preview.v1"

ProfilePolicyReason = Literal[
    "pinned_non_profile",
    "important_non_profile",
    "reused_non_profile",
    "profile_overlong",
    "profile_low_confidence",
]


@dataclass(frozen=True)
class ProfilePolicyItem:
    fact: Fact
    reasons: tuple[ProfilePolicyReason, ...]
    recommendation: str


@dataclass(frozen=True)
class ProfilePolicyPreview:
    policy_version: str
    char_budget: int
    fact_char_budget: int
    current_count: int
    current_chars: int
    over_budget: bool
    candidates: list[ProfilePolicyItem]
    issues: list[ProfilePolicyItem]


def profile_policy_preview(
    *,
    profile_facts: list[Fact],
    review_facts: list[Fact],
    char_budget: int = DEFAULT_PROFILE_CHAR_BUDGET,
    fact_char_budget: int = DEFAULT_PROFILE_FACT_CHAR_BUDGET,
    review_access_count: int = DEFAULT_PROFILE_REVIEW_ACCESS_COUNT,
) -> ProfilePolicyPreview:
    budget = max(1, char_budget)
    per_fact_budget = max(1, fact_char_budget)
    access_count = max(1, review_access_count)
    current_chars = sum(len(fact.text) for fact in profile_facts)

    return ProfilePolicyPreview(
        policy_version=PROFILE_POLICY_VERSION,
        char_budget=budget,
        fact_char_budget=per_fact_budget,
        current_count=len(profile_facts),
        current_chars=current_chars,
        over_budget=current_chars > budget,
        candidates=[
            item
            for fact in review_facts
            if (item := _review_candidate(fact, review_access_count=access_count)) is not None
        ],
        issues=[
            item
            for fact in profile_facts
            if (item := _profile_issue(fact, fact_char_budget=per_fact_budget)) is not None
        ],
    )


def _review_candidate(fact: Fact, *, review_access_count: int) -> ProfilePolicyItem | None:
    reasons: list[ProfilePolicyReason] = []
    if fact.pinned_at is not None:
        reasons.append("pinned_non_profile")
    if fact.salience >= 2:
        reasons.append("important_non_profile")
    if fact.salience >= 1 and fact.access_count >= review_access_count:
        reasons.append("reused_non_profile")

    if not reasons:
        return None

    return ProfilePolicyItem(
        fact=fact,
        reasons=tuple(reasons),
        recommendation=_candidate_recommendation(reasons),
    )


def _profile_issue(fact: Fact, *, fact_char_budget: int) -> ProfilePolicyItem | None:
    reasons: list[ProfilePolicyReason] = []
    if len(fact.text) > fact_char_budget:
        reasons.append("profile_overlong")
    if fact.confidence < 0.7:
        reasons.append("profile_low_confidence")

    if not reasons:
        return None

    return ProfilePolicyItem(
        fact=fact,
        reasons=tuple(reasons),
        recommendation=_issue_recommendation(reasons),
    )


def _candidate_recommendation(reasons: list[ProfilePolicyReason]) -> str:
    if "pinned_non_profile" in reasons:
        return "review the fact kind; pinned always-visible memory needs a profile kind"
    if "important_non_profile" in reasons:
        return "review whether this should be identity, preference, relationship, or constraint"
    return "review repeated use before promoting this fact to profile memory"


def _issue_recommendation(reasons: list[ProfilePolicyReason]) -> str:
    if "profile_overlong" in reasons:
        return "split or shorten this profile fact before expanding profile budget"
    if "profile_low_confidence" in reasons:
        return "verify the source fact before treating it as always-visible memory"
    return "review profile fact"
