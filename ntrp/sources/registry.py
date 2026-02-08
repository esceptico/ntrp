from dataclasses import dataclass
from typing import Any, Protocol

from ntrp.config import Config
from ntrp.sources.browser import BrowserHistorySource
from ntrp.sources.exa import WebSource
from ntrp.sources.google.auth import discover_calendar_tokens, discover_gmail_tokens
from ntrp.sources.google.calendar import MultiCalendarSource
from ntrp.sources.google.gmail import MultiGmailSource
from ntrp.sources.obsidian import ObsidianSource


class SourceSpec(Protocol):
    name: str

    def enabled(self, config: Config) -> bool: ...

    def create(self, config: Config) -> Any | None: ...


@dataclass(frozen=True)
class ObsidianSpec:
    name: str = "notes"

    def enabled(self, config: Config) -> bool:
        return config.vault_path is not None

    def create(self, config: Config):
        return ObsidianSource(vault_path=config.vault_path)


@dataclass(frozen=True)
class GmailSpec:
    name: str = "email"

    def enabled(self, config: Config) -> bool:
        return config.gmail

    def create(self, config: Config):
        token_paths = discover_gmail_tokens()
        if not token_paths:
            return None
        source = MultiGmailSource(token_paths=token_paths, days_back=config.gmail_days)
        return source if source.sources else None


@dataclass(frozen=True)
class CalendarSpec:
    name: str = "calendar"

    def enabled(self, config: Config) -> bool:
        return config.calendar

    def create(self, config: Config):
        token_paths = discover_calendar_tokens()
        if not token_paths:
            return None
        return MultiCalendarSource(token_paths=token_paths, days_back=7, days_ahead=30)


@dataclass(frozen=True)
class BrowserSpec:
    name: str = "browser"

    def enabled(self, config: Config) -> bool:
        return config.browser is not None

    def create(self, config: Config):
        return BrowserHistorySource(
            browser_name=config.browser,
            days_back=config.browser_days,
        )


@dataclass(frozen=True)
class WebSpec:
    name: str = "web"

    def enabled(self, config: Config) -> bool:
        return config.exa_api_key is not None

    def create(self, config: Config):
        return WebSource(api_key=config.exa_api_key)


SOURCES: dict[str, SourceSpec] = {
    spec.name: spec
    for spec in [
        ObsidianSpec(),
        GmailSpec(),
        CalendarSpec(),
        BrowserSpec(),
        WebSpec(),
    ]
}
