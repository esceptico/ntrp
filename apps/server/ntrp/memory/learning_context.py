from typing import TYPE_CHECKING

from ntrp.memory.models import LearningCandidate

if TYPE_CHECKING:
    from ntrp.memory.facts import FactMemory

RUNTIME_LEARNING_CONTEXT_CHANGE_TYPES = frozenset({"skill_note", "prompt_note"})
MEMORY_POLICY_CONTEXT_CHANGE_TYPES = frozenset(
    {
        "memory_feedback",
        "injection_rule",
        "recall_rule",
        "prune_rule",
    }
)
AUTOMATION_POLICY_CONTEXT_CHANGE_TYPES = frozenset({"automation_rule"})

APPROVED_LEARNING_CONTEXT_CHANGE_TYPES = RUNTIME_LEARNING_CONTEXT_CHANGE_TYPES
APPROVED_LEARNING_CONTEXT_STATUSES = ("approved", "applied")
APPLIED_POLICY_CONTEXT_STATUSES = ("applied",)
DEFAULT_LEARNING_CONTEXT_LIMIT = 8
DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET = 1200


def format_learning_context(
    candidates: list[LearningCandidate],
    *,
    char_budget: int = DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET,
    change_types: frozenset[str] = APPROVED_LEARNING_CONTEXT_CHANGE_TYPES,
    statuses: tuple[str, ...] = APPROVED_LEARNING_CONTEXT_STATUSES,
    target_prefixes: tuple[str, ...] = (),
) -> str | None:
    lines = [
        f"- {candidate.target_key}: {candidate.proposal}"
        for candidate in candidates
        if candidate.status in statuses
        and candidate.change_type in change_types
        and _matches_target_prefix(candidate.target_key, target_prefixes)
    ]
    if not lines:
        return None

    selected: list[str] = []
    used_chars = 0
    for line in lines:
        next_chars = len(line) + 1
        if selected and used_chars + next_chars > char_budget:
            break
        if not selected and next_chars > char_budget:
            selected.append(_truncate_line(line, char_budget))
            break
        selected.append(line)
        used_chars += next_chars

    return "\n".join(selected) if selected else None


def _matches_target_prefix(target_key: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    return any(target_key.startswith(prefix) for prefix in prefixes)


def _truncate_line(line: str, char_budget: int) -> str:
    if len(line) <= char_budget:
        return line
    if char_budget <= 3:
        return line[:char_budget]
    return f"{line[: char_budget - 3]}..."


async def get_approved_learning_context(
    memory: "FactMemory",
    *,
    limit: int = DEFAULT_LEARNING_CONTEXT_LIMIT,
    char_budget: int = DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET,
) -> str | None:
    return await get_learning_context(
        memory,
        change_types=RUNTIME_LEARNING_CONTEXT_CHANGE_TYPES,
        statuses=APPROVED_LEARNING_CONTEXT_STATUSES,
        limit=limit,
        char_budget=char_budget,
    )


async def get_applied_memory_policy_context(
    memory: "FactMemory",
    *,
    limit: int = DEFAULT_LEARNING_CONTEXT_LIMIT,
    char_budget: int = DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET,
    target_prefixes: tuple[str, ...] = (),
) -> str | None:
    return await get_learning_context(
        memory,
        change_types=MEMORY_POLICY_CONTEXT_CHANGE_TYPES,
        statuses=APPLIED_POLICY_CONTEXT_STATUSES,
        limit=limit,
        char_budget=char_budget,
        target_prefixes=target_prefixes,
    )


async def get_applied_automation_policy_context(
    memory: "FactMemory",
    *,
    automation_id: str | None = None,
    limit: int = DEFAULT_LEARNING_CONTEXT_LIMIT,
    char_budget: int = DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET,
) -> str | None:
    prefixes = ("automation.review",)
    if automation_id:
        prefixes = (f"automation.{automation_id}", *prefixes)
    return await get_learning_context(
        memory,
        change_types=AUTOMATION_POLICY_CONTEXT_CHANGE_TYPES,
        statuses=APPLIED_POLICY_CONTEXT_STATUSES,
        limit=limit,
        char_budget=char_budget,
        target_prefixes=prefixes,
    )


async def get_learning_context(
    memory: "FactMemory",
    *,
    change_types: frozenset[str],
    statuses: tuple[str, ...],
    limit: int = DEFAULT_LEARNING_CONTEXT_LIMIT,
    char_budget: int = DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET,
    target_prefixes: tuple[str, ...] = (),
) -> str | None:
    candidates: list[LearningCandidate] = []
    for status in statuses:
        for change_type in change_types:
            candidates.extend(
                await memory.learning.list_candidates(
                    limit=limit,
                    status=status,
                    change_type=change_type,
                )
            )

    candidates.sort(key=lambda candidate: (candidate.created_at, candidate.id), reverse=True)
    selected = [
        candidate
        for candidate in candidates
        if candidate.status in statuses
        and candidate.change_type in change_types
        and _matches_target_prefix(candidate.target_key, target_prefixes)
    ][:limit]
    return format_learning_context(
        selected,
        char_budget=char_budget,
        change_types=change_types,
        statuses=statuses,
        target_prefixes=target_prefixes,
    )
