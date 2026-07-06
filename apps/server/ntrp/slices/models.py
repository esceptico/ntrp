from dataclasses import dataclass, field
from typing import Literal

AskKind = Literal["review", "decide", "act", "drift"]
AskState = Literal["active", "done", "dismissed", "snoozed"]
Autonomy = Literal["observe", "act"]


@dataclass
class Slice:
    key: str
    title: str
    page_path: str  # vault-relative, e.g. "topics/o-1a.md"
    autonomy: Autonomy
    related: list[str] = field(default_factory=list)


@dataclass
class Ask:
    id: str
    slice_key: str
    text: str
    kind: AskKind
    source: str  # "approval" | "run_failed" | "agent_output" | "open_loop" | "agent"
    actions: list[dict]  # [{"verb": "open_session", "ref": "<id>"}, ...]
    state: AskState
    created_at: str  # ISO
    snoozed_until: str | None = None
    provenance: str | None = None  # run/source that produced it
