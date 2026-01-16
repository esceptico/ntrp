from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionState:
    session_id: str
    started_at: datetime
    user_id: str
    current_task: str | None = None
    gathered_context: list[dict] = field(default_factory=list)
    pending_actions: list[dict] = field(default_factory=list)
    last_compaction_turn: int = 0
    rolling_summary: str = ""
    last_activity: datetime = field(default_factory=datetime.now)
    approved_patterns: dict[str, set[str]] = field(default_factory=dict)
    auto_approve: set[str] = field(default_factory=set)
    yolo: bool = False


@dataclass
class SessionData:
    state: SessionState
    messages: list[dict]
