"""Missed-run catch-up: daily maintenance builtins that miss their slot while
the machine is asleep must run on boot, not skip to tomorrow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ntrp.automation.models import Automation
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.triggers import TimeTrigger

NOW = datetime(2026, 6, 18, 9, 0, tzinfo=UTC)


def _auto(**kw) -> Automation:
    base = dict(
        task_id="t", name="n", description="d", model=None,
        triggers=[TimeTrigger(at="03:00", days="daily")], enabled=True,
        created_at=NOW, next_run_at=NOW - timedelta(hours=6), last_run_at=None,
        last_result=None, running_since=None, auto_approve=True,
        handler="memory_consolidate", builtin=True, cooldown_minutes=None,
    )
    base.update(kw)
    return Automation(**base)


def test_catch_up_when_never_run():
    assert Scheduler._should_catch_up_missed(_auto(last_run_at=None), NOW) is True


def test_catch_up_when_stale_beyond_cadence():
    assert Scheduler._should_catch_up_missed(_auto(last_run_at=NOW - timedelta(hours=30)), NOW) is True


def test_no_catch_up_when_recently_run():
    assert Scheduler._should_catch_up_missed(_auto(last_run_at=NOW - timedelta(hours=2)), NOW) is False


def test_no_catch_up_for_user_automation():
    assert Scheduler._should_catch_up_missed(_auto(builtin=False), NOW) is False


def test_no_catch_up_for_other_builtin_handler():
    assert Scheduler._should_catch_up_missed(_auto(handler="automation_suggester_daily"), NOW) is False


def test_no_catch_up_for_memory_publish_handler():
    assert Scheduler._should_catch_up_missed(_auto(handler="memory_publish"), NOW) is False


def test_no_catch_up_with_extra_triggers():
    two = [TimeTrigger(at="03:00", days="daily"), TimeTrigger(at="15:00", days="daily")]
    assert Scheduler._should_catch_up_missed(_auto(triggers=two), NOW) is False
