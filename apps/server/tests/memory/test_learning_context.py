from datetime import UTC, datetime

from ntrp.core.prompts import build_system_prompt
from ntrp.memory.learning_context import (
    APPLIED_POLICY_CONTEXT_STATUSES,
    MEMORY_POLICY_CONTEXT_CHANGE_TYPES,
    format_learning_context,
)
from ntrp.memory.models import LearningCandidate


def _candidate(
    *,
    change_type: str,
    target_key: str,
    proposal: str,
    status: str = "approved",
) -> LearningCandidate:
    now = datetime.now(UTC)
    return LearningCandidate(
        id=1,
        created_at=now,
        updated_at=now,
        status=status,
        change_type=change_type,
        target_key=target_key,
        proposal=proposal,
        rationale="test",
        evidence_event_ids=[],
        expected_metric=None,
        policy_version="test",
    )


def test_learning_context_formats_only_procedural_candidates():
    context = format_learning_context(
        [
            _candidate(change_type="skill_note", target_key="skill.release", proposal="Check rc tags first."),
            _candidate(
                change_type="prompt_note", target_key="prompt.memory", proposal="Treat corrections as evidence."
            ),
            _candidate(change_type="memory_feedback", target_key="memory.prune", proposal="Review prune rules."),
        ]
    )

    assert context is not None
    assert "skill.release: Check rc tags first." in context
    assert "prompt.memory: Treat corrections as evidence." in context
    assert "memory.prune" not in context


def test_policy_context_formats_only_applied_policy_candidates():
    context = format_learning_context(
        [
            _candidate(
                change_type="memory_feedback",
                target_key="memory.extraction.feedback",
                proposal="Avoid current-task facts unless explicitly reusable.",
                status="applied",
            ),
            _candidate(
                change_type="memory_feedback",
                target_key="memory.prune.feedback",
                proposal="Review deleted patterns.",
                status="approved",
            ),
            _candidate(
                change_type="prompt_note",
                target_key="prompt.memory",
                proposal="This belongs to runtime prompts.",
                status="applied",
            ),
        ],
        change_types=MEMORY_POLICY_CONTEXT_CHANGE_TYPES,
        statuses=APPLIED_POLICY_CONTEXT_STATUSES,
        target_prefixes=("memory.extraction.",),
    )

    assert context == "- memory.extraction.feedback: Avoid current-task facts unless explicitly reusable."


def test_learning_context_respects_char_budget():
    context = format_learning_context(
        [
            _candidate(change_type="skill_note", target_key="skill.a", proposal="short"),
            _candidate(change_type="skill_note", target_key="skill.b", proposal="this one is too long"),
        ],
        char_budget=18,
    )

    assert context == "- skill.a: short"


def test_learning_context_truncates_single_large_note():
    context = format_learning_context(
        [
            _candidate(change_type="skill_note", target_key="skill.large", proposal="x" * 80),
        ],
        char_budget=24,
    )

    assert context == "- skill.large: xxxxxx..."


def test_system_prompt_includes_learning_context():
    prompt = build_system_prompt(
        source_details={},
        learning_context="- skill.release: Check rc tags first.",
    )

    assert "## APPROVED LEARNING NOTES" in prompt
    assert "- skill.release: Check rc tags first." in prompt
