from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class SessionState:
    session_id: str
    started_at: datetime
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    name: str | None = None
    auto_approve: set[str] = field(default_factory=set)
    skip_approvals: bool = False
    session_type: Literal["chat", "channel"] = "chat"
    origin_automation_id: str | None = None


@dataclass
class SessionData:
    state: SessionState
    messages: list[dict]
    last_input_tokens: int | None = None
