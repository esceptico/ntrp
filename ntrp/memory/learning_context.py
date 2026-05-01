from ntrp.memory.facts import FactMemory
from ntrp.memory.models import LearningCandidate

APPROVED_LEARNING_CONTEXT_CHANGE_TYPES = frozenset({"skill_note", "prompt_note"})
APPROVED_LEARNING_CONTEXT_STATUSES = ("approved", "applied")
DEFAULT_LEARNING_CONTEXT_LIMIT = 8
DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET = 1200


def format_learning_context(
    candidates: list[LearningCandidate],
    *,
    char_budget: int = DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET,
) -> str | None:
    lines = [
        f"- {candidate.target_key}: {candidate.proposal}"
        for candidate in candidates
        if candidate.status in APPROVED_LEARNING_CONTEXT_STATUSES
        and candidate.change_type in APPROVED_LEARNING_CONTEXT_CHANGE_TYPES
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


def _truncate_line(line: str, char_budget: int) -> str:
    if len(line) <= char_budget:
        return line
    if char_budget <= 3:
        return line[:char_budget]
    return f"{line[: char_budget - 3]}..."


async def get_approved_learning_context(
    memory: FactMemory,
    *,
    limit: int = DEFAULT_LEARNING_CONTEXT_LIMIT,
    char_budget: int = DEFAULT_LEARNING_CONTEXT_CHAR_BUDGET,
) -> str | None:
    candidates: list[LearningCandidate] = []
    for status in APPROVED_LEARNING_CONTEXT_STATUSES:
        for change_type in APPROVED_LEARNING_CONTEXT_CHANGE_TYPES:
            candidates.extend(
                await memory.learning.list_candidates(
                    limit=limit,
                    status=status,
                    change_type=change_type,
                )
            )

    candidates.sort(key=lambda candidate: (candidate.created_at, candidate.id), reverse=True)
    return format_learning_context(candidates[:limit], char_budget=char_budget)
