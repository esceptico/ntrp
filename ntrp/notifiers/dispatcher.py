from collections.abc import Callable

from ntrp.channel import Handler
from ntrp.core.events import ScheduleCompleted
from ntrp.logging import get_logger
from ntrp.notifiers.base import Notifier

_logger = get_logger(__name__)


def make_schedule_dispatcher(
    get_notifiers: Callable[[], dict[str, Notifier]],
) -> Handler[ScheduleCompleted]:
    """Subscribe once to ScheduleCompleted on Channel.

    Calls get_notifiers() at dispatch time to resolve the current registry.
    Each task declares which channels it wants (task.notifiers); the dispatcher
    matches those names against the registry and calls send() on each match.
    """

    async def dispatch(event: ScheduleCompleted) -> None:
        notifiers = get_notifiers()
        for name in event.task.notifiers:
            notifier = notifiers.get(name)
            if not notifier:
                _logger.warning("No notifier registered for channel %r", name)
                continue
            subject = f"[ntrp] {event.task.name}" if event.task.name else "[ntrp]"
            body = event.result or "(no output)"
            try:
                await notifier.send(subject, body)
            except Exception:
                _logger.exception("Notifier %r failed for task %s", name, event.task.task_id)

    return dispatch
