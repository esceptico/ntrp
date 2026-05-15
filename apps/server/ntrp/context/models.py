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
    # Size of the agent's working-set after the most recent run. Equals
    # `len(messages)` for ordinary chats, but loops trim history to a tail
    # window before each tick — `messages` on disk grows much larger than
    # what the agent (and the compactor) actually sees. The desktop's
    # budget dial uses this for the message-pressure scale so it reflects
    # what's actually heading into the next LLM call.
    last_message_count: int | None = None
