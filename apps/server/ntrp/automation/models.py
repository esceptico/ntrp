from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from ntrp.automation.triggers import Trigger

AutomationKind = Literal["automation", "loop"]


@dataclass
class Automation:
    task_id: str
    name: str
    description: str
    model: str | None
    triggers: list[Trigger]
    enabled: bool
    created_at: datetime
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_result: str | None
    running_since: datetime | None
    writable: bool
    handler: str | None = None
    builtin: bool = False
    cooldown_minutes: int | None = None
    kind: AutomationKind = "automation"
    target_session_id: str | None = None
    loop_prompt: str | None = None
    max_iterations: int | None = None
    iteration_count: int = 0
    stop_when: str | None = None
    max_age_days: int | None = None

    def in_cooldown(self, now: datetime) -> bool:
        if not self.cooldown_minutes or not self.last_run_at:
            return False
        return (now - self.last_run_at) < timedelta(minutes=self.cooldown_minutes)

    def aged_out(self, now: datetime) -> bool:
        if not self.max_age_days:
            return False
        return (now - self.created_at) >= timedelta(days=self.max_age_days)
