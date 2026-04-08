from ntrp.config import Config
from ntrp.integrations.base import Integration
from ntrp.integrations.calendar.client import MultiCalendarSource
from ntrp.integrations.calendar.tools import (
    CalendarTool,
    CreateCalendarEventTool,
    DeleteCalendarEventTool,
    EditCalendarEventTool,
)
from ntrp.integrations.google_auth.auth import discover_calendar_tokens


def _build(config: Config) -> MultiCalendarSource | None:
    if not config.google:
        return None
    token_paths = discover_calendar_tokens()
    if not token_paths:
        return None
    source = MultiCalendarSource(token_paths=token_paths, days_back=7, days_ahead=30)
    return source if source.sources else None


CALENDAR = Integration(
    id="calendar",
    label="Google Calendar",
    tools=[CalendarTool, CreateCalendarEventTool, EditCalendarEventTool, DeleteCalendarEventTool],
    build=_build,
)
