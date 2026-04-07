from collections.abc import Callable

from ntrp.config import Config
from ntrp.sources.google.auth import discover_calendar_tokens, discover_gmail_tokens
from ntrp.sources.google.calendar import MultiCalendarSource
from ntrp.sources.google.gmail import MultiGmailSource


def _create_gmail(config: Config) -> object | None:
    if not config.google:
        return None
    token_paths = discover_gmail_tokens()
    if not token_paths:
        return None
    source = MultiGmailSource(token_paths=token_paths, days_back=config.gmail_days)
    return source if source.sources else None


def _create_calendar(config: Config) -> object | None:
    if not config.google:
        return None
    token_paths = discover_calendar_tokens()
    if not token_paths:
        return None
    source = MultiCalendarSource(token_paths=token_paths, days_back=7, days_ahead=30)
    return source if source.sources else None


SOURCES: dict[str, Callable[[Config], object | None]] = {
    "gmail": _create_gmail,
    "calendar": _create_calendar,
}
