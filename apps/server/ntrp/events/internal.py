from dataclasses import dataclass

from ntrp.agent import Usage

# --- Run lifecycle ---


@dataclass(frozen=True)
class RunCompleted:
    run_id: str
    session_id: str
    messages: tuple[dict, ...]
    usage: Usage
    result: str | None
    source_refs: tuple[dict, ...] = ()
