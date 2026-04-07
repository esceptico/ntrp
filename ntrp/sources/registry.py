from collections.abc import Callable

from ntrp.config import Config
from ntrp.sources.google.auth import discover_calendar_tokens, discover_gmail_tokens
from ntrp.sources.google.calendar import MultiCalendarSource
from ntrp.sources.google.gmail import MultiGmailSource
from ntrp.sources.obsidian import ObsidianSource
from ntrp.sources.slack import SlackSource


def _create_notes(config: Config) -> object | None:
    if config.vault_path is None:
        return None
    return ObsidianSource(vault_path=config.vault_path)


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


def _create_web(config: Config) -> object | None:
    mode = config.web_search
    if mode == "none":
        return None
    if mode == "ddgs":
        from ntrp.sources.ddgs import DDGSWebSource

        return DDGSWebSource()
    if mode == "exa":
        if config.exa_api_key is None:
            raise ValueError("WEB_SEARCH=exa requires EXA_API_KEY")
        from ntrp.sources.exa import ExaWebSource

        return ExaWebSource(api_key=config.exa_api_key)

    # auto: prefer Exa when configured, otherwise default to DDGS
    if config.exa_api_key:
        from ntrp.sources.exa import ExaWebSource

        return ExaWebSource(api_key=config.exa_api_key)
    from ntrp.sources.ddgs import DDGSWebSource

    return DDGSWebSource()


def _create_slack(config: Config) -> object | None:
    if not config.slack_bot_token and not config.slack_user_token:
        return None
    return SlackSource(bot_token=config.slack_bot_token, user_token=config.slack_user_token)


SOURCES: dict[str, Callable[[Config], object | None]] = {
    "notes": _create_notes,
    "gmail": _create_gmail,
    "calendar": _create_calendar,
    "web": _create_web,
    "slack": _create_slack,
}
