from ntrp.memory.source_refs import chat_message_range_ref, chat_segment_ref, parse_source_ref


def test_parse_chat_segment_ref():
    ref = chat_segment_ref("session-123", 4, 9)

    assert parse_source_ref(ref) == {
        "kind": "chat_segment",
        "session_id": "session-123",
        "message_start": 4,
        "message_end": 9,
    }


def test_parse_chat_message_range_ref():
    ref = chat_message_range_ref("session-123", "msg-a", "msg-b")

    assert parse_source_ref(ref) == {
        "kind": "chat_message_range",
        "session_id": "session-123",
        "message_start_id": "msg-a",
        "message_end_id": "msg-b",
    }


def test_parse_source_ref_rejects_unknown_or_invalid_refs():
    assert parse_source_ref(None) is None
    assert parse_source_ref("note.md") is None
    assert parse_source_ref("chat:session-123:not-a-range") is None
    assert parse_source_ref("chat:session-123:9-4") is None
    assert parse_source_ref("chatmsg:session-123:missing-end") is None
