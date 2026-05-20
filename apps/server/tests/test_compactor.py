from ntrp.agent import Role
from ntrp.constants import SESSION_HANDOFF_MARKER
from ntrp.core.compactor import (
    SummaryCompactor,
    _build_compacted_messages,
    compact_needed,
    estimate_message_tokens,
    is_handoff_message,
)


def test_handoff_summary_tracks_raw_message_range():
    messages = [
        {"role": Role.SYSTEM, "content": "system", "message_id": "sys"},
        {"role": Role.USER, "content": "first", "message_id": "m-1"},
        {"role": Role.ASSISTANT, "content": "reply", "message_id": "m-2"},
        {"role": Role.USER, "content": "second", "message_id": "m-3"},
        {"role": Role.ASSISTANT, "content": "tail", "message_id": "m-4"},
    ]

    compacted = _build_compacted_messages(messages, 1, 4, "Useful summary")

    summary = compacted[1]
    assert summary["content"] == f"{SESSION_HANDOFF_MARKER}\nUseful summary"
    assert summary["compaction"] == {
        "kind": "session_handoff",
        "message_start": 1,
        "message_end": 4,
        "message_start_id": "m-1",
        "message_end_id": "m-3",
    }
    assert is_handoff_message(summary)


def test_build_compacted_messages_embeds_rehydration_state():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "old", "message_id": "m1"},
        {"role": "assistant", "content": "new", "message_id": "m2"},
    ]
    state = {"active_plan_ref": "plan:abc", "pending_approval_ids": ["call-1"]}

    compacted = _build_compacted_messages(messages, 1, 2, "summary", rehydration_state=state)

    assert compacted[1]["compaction"]["rehydration"] == state


def _large_history(message_count: int = 10, chars_per_message: int = 45_000) -> list[dict]:
    return [
        {"role": "system", "content": "system"},
        *[
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"msg-{i} " + ("x" * chars_per_message),
            }
            for i in range(message_count)
        ],
    ]


def test_compact_needed_uses_local_estimate_when_usage_missing():
    messages = _large_history()

    assert estimate_message_tokens(messages) > 100_000
    assert compact_needed(messages, "gpt-5.2", actual_input_tokens=None, threshold=0.01)


def test_compact_needed_uses_estimate_when_saved_usage_is_stale_low():
    messages = _large_history()

    assert compact_needed(messages, "gpt-5.2", actual_input_tokens=1_000, threshold=0.01)


def test_summary_compactor_triggers_with_missing_usage_for_oversized_history():
    messages = _large_history()
    compactor = SummaryCompactor(threshold=0.01)

    assert compactor.should_compact(messages, "gpt-5.2", last_input_tokens=None)


def test_compact_needed_does_not_compact_small_history_from_estimate():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "small"},
        {"role": "assistant", "content": "ok"},
    ]

    assert not compact_needed(messages, "gpt-5.2", actual_input_tokens=None)
