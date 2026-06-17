import json


def parse_sse_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for chunk in raw.split("\n\n"):
        data_line = next((line for line in chunk.splitlines() if line.startswith("data:")), None)
        if data_line is None:
            continue
        payload = data_line.removeprefix("data:").strip()
        if payload:
            events.append(json.loads(payload))
    return events
