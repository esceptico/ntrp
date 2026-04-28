from dataclasses import asdict

from ntrp.agent import Usage
from ntrp.events.internal import RunCompleted

OUTBOX_RUN_COMPLETED = "run.completed"


def run_completed_payload(event: RunCompleted) -> dict:
    return {
        "run_id": event.run_id,
        "session_id": event.session_id,
        "messages": list(event.messages),
        "usage": asdict(event.usage),
        "result": event.result,
    }


def run_completed_from_payload(payload: dict) -> RunCompleted:
    usage = payload.get("usage") or {}
    return RunCompleted(
        run_id=payload["run_id"],
        session_id=payload["session_id"],
        messages=tuple(payload.get("messages") or ()),
        usage=Usage(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            cache_read_tokens=int(usage.get("cache_read_tokens", 0)),
            cache_write_tokens=int(usage.get("cache_write_tokens", 0)),
        ),
        result=payload.get("result"),
    )
