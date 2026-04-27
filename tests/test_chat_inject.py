import json

from ntrp.events.sse import MessageIngestedEvent


def test_message_ingested_event_serialization():
    event = MessageIngestedEvent(client_id="abc-123", run_id="cool-otter")
    sse = event.to_sse_string()
    assert "event: message_ingested" in sse
    payload = json.loads(sse.split("data: ", 1)[1].strip())
    assert payload == {
        "type": "message_ingested",
        "client_id": "abc-123",
        "run_id": "cool-otter",
    }
