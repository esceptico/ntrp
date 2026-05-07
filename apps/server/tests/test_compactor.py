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
