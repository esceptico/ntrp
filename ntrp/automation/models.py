from dataclasses import dataclass
from datetime import datetime, timedelta

from ntrp.automation.triggers import Trigger


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
    notifiers: list[str]
    last_result: str | None
    running_since: datetime | None
    writable: bool
    handler: str | None = None
    builtin: bool = False
    cooldown_minutes: int | None = None

    def in_cooldown(self, now: datetime) -> bool:
        if not self.cooldown_minutes or not self.last_run_at:
            return False
        return (now - self.last_run_at) < timedelta(minutes=self.cooldown_minutes)
