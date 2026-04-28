from dataclasses import asdict

from ntrp.agent import Usage
from ntrp.events.internal import FactDeleted, FactUpdated, MemoryCleared, RunCompleted

OUTBOX_FACT_INDEX_DELETE = "memory.fact.index.delete"
OUTBOX_FACT_INDEX_UPSERT = "memory.fact.index.upsert"
OUTBOX_MEMORY_INDEX_CLEAR = "memory.index.clear"
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


def fact_index_upsert_payload(fact_id: int, text: str) -> dict:
    return {"fact_id": fact_id, "text": text}


def fact_updated_from_payload(payload: dict) -> FactUpdated:
    return FactUpdated(fact_id=int(payload["fact_id"]), text=payload["text"])


def fact_index_delete_payload(fact_id: int) -> dict:
    return {"fact_id": fact_id}


def fact_deleted_from_payload(payload: dict) -> FactDeleted:
    return FactDeleted(fact_id=int(payload["fact_id"]))


def memory_cleared_from_payload(_payload: dict) -> MemoryCleared:
    return MemoryCleared()
