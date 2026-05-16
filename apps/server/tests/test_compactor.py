from ntrp.agent import Role
from ntrp.constants import SESSION_HANDOFF_MARKER
from ntrp.core.compactor import _build_compacted_messages, is_handoff_message


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
