from collections.abc import Callable

from ntrp.config import Config
from ntrp.sources.base import Source
from ntrp.sources.browser import BrowserHistorySource
from ntrp.sources.exa import WebSource
from ntrp.sources.google.auth import discover_calendar_tokens, discover_gmail_tokens
from ntrp.sources.google.calendar import MultiCalendarSource
from ntrp.sources.google.gmail import MultiGmailSource
from ntrp.sources.obsidian import ObsidianSource

SourceEntry = tuple[Callable[[Config], bool], Callable[[Config], Source | None]]


def _create_gmail(config: Config):
    token_paths = discover_gmail_tokens()
    if not token_paths:
        return None
    source = MultiGmailSource(token_paths=token_paths, days_back=config.gmail_days)
    return source if source.sources else None


def _create_calendar(config: Config):
    token_paths = discover_calendar_tokens()
    if not token_paths:
        return None
    return MultiCalendarSource(token_paths=token_paths, days_back=7, days_ahead=30)


SOURCES: dict[str, SourceEntry] = {
    "notes": (
        lambda c: c.vault_path is not None,
        lambda c: ObsidianSource(vault_path=c.vault_path),
    ),
    "email": (
        lambda c: c.gmail,
        _create_gmail,
    ),
    "calendar": (
        lambda c: c.calendar,
        _create_calendar,
    ),
    "browser": (
        lambda c: c.browser is not None,
        lambda c: BrowserHistorySource(browser_name=c.browser, days_back=c.browser_days),
    ),
    "web": (
        lambda c: c.exa_api_key is not None,
        lambda c: WebSource(api_key=c.exa_api_key),
    ),
}
