from dataclasses import dataclass
from datetime import datetime

from ntrp.automation.triggers import Trigger, build_trigger, parse_trigger

__all__ = ["Automation", "Trigger", "build_trigger", "parse_trigger"]


@dataclass
class Automation:
    task_id: str
    name: str
    description: str
    model: str | None
    trigger: Trigger
    enabled: bool
    created_at: datetime
    next_run_at: datetime | None
    last_run_at: datetime | None
    notifiers: list[str]
    last_result: str | None
    running_since: datetime | None
    writable: bool
