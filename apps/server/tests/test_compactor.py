import asyncio
import time
from types import SimpleNamespace

import pytest

import ntrp.constants as constants
from ntrp.agent import Role
from ntrp.constants import SESSION_HANDOFF_MARKER
from ntrp.core.compactor import (
    SummaryCompactor,
    _build_compacted_messages,
    compact_needed,
    compact_summarize,
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


def test_compact_needed_requires_usage_or_message_ceiling():
    messages = _large_history()

    assert not compact_needed(messages, "gpt-5.2", actual_input_tokens=None, threshold=0.01, max_messages=999)


def test_compact_needed_trusts_saved_usage_when_present():
    messages = _large_history()

    assert not compact_needed(messages, "gpt-5.2", actual_input_tokens=1_000, threshold=0.01)


def test_compact_needed_uses_headroom_before_configured_threshold(monkeypatch):
    monkeypatch.setattr(
        "ntrp.core.compactor.get_model",
        lambda _model: type("Model", (), {"max_context_tokens": 1000})(),
    )
    messages = [{"role": "system", "content": "system"}]

    assert compact_needed(messages, "test-model", actual_input_tokens=760, threshold=0.8)
    assert not compact_needed(messages, "test-model", actual_input_tokens=759, threshold=0.8)


def test_compact_needed_triggers_at_message_ceiling():
    messages = [{"role": "user", "content": str(i)} for i in range(5)]

    assert compact_needed(messages, "gpt-5.2", actual_input_tokens=0, max_messages=5)


def test_summary_compactor_waits_for_usage_or_message_ceiling():
    messages = _large_history()
    compactor = SummaryCompactor(threshold=0.01, max_messages=999)

    assert not compactor.should_compact(messages, "gpt-5.2", last_input_tokens=None)


def test_compaction_timeout_is_finite():
    assert constants.COMPACTION_TIMEOUT is not None
    assert constants.COMPACTION_TIMEOUT > 0


@pytest.mark.asyncio
async def test_compact_summarize_keeps_server_event_loop_responsive(monkeypatch):
    class BlockingClient:
        async def completion(self, **_kwargs):
            time.sleep(0.1)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))],
            )

        async def close(self):
            return None

    monkeypatch.setattr("ntrp.core.compactor.create_completion_client", lambda _model: BlockingClient())

    messages = [
        {"role": Role.SYSTEM, "content": "system"},
        {"role": Role.USER, "content": "old"},
        {"role": Role.ASSISTANT, "content": "reply"},
        {"role": Role.USER, "content": "tail"},
        {"role": Role.ASSISTANT, "content": "tail reply"},
    ]

    started = time.perf_counter()
    task = asyncio.create_task(compact_summarize(messages, 1, 3, "gpt-5.2"))
    await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.05)

    assert time.perf_counter() - started < 0.05
    assert await task == "summary"
