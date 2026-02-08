from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class SessionState:
    session_id: str
    started_at: datetime
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    auto_approve: set[str] = field(default_factory=set)
    skip_approvals: bool = False


@dataclass
class SessionData:
    state: SessionState
    messages: list[dict]
