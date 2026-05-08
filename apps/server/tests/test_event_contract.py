import json

from ntrp.events.sse import RunCancelledEvent, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ntrp.server.bus import StreamRecord, stream_record_to_sse_string


def _payload(event):
    record = StreamRecord(session_id="sess-1", seq=1, event=event)
    frame = stream_record_to_sse_string("sess-1", record)
    return json.loads(frame.split("data: ", 1)[1].strip())


def test_terminal_events_identify_run_session_and_sequence():
    events = [
        RunStartedEvent(session_id="sess-1", run_id="run-1"),
        RunFinishedEvent(run_id="run-1"),
        RunCancelledEvent(run_id="run-1"),
        RunErrorEvent(run_id="run-1", message="failed"),
    ]

    for event in events:
        payload = _payload(event)
        assert payload["session_id"] == "sess-1"
        assert payload["seq"] == 1
        assert payload["run_id"] == "run-1"


def test_stream_record_uses_sse_id_as_cursor():
    record = StreamRecord(session_id="sess-1", seq=44, event=RunFinishedEvent(run_id="run-1"))
    frame = stream_record_to_sse_string("sess-1", record)

    assert frame.startswith("id: 44\n")
    assert "event: RUN_FINISHED\n" in frame
