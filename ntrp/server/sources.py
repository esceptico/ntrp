from ntrp.channel import Channel
from ntrp.config import Config
from ntrp.logging import get_logger
from ntrp.sources.base import Source
from ntrp.events import SourceChanged
from ntrp.sources.registry import SOURCES

_logger = get_logger(__name__)


class SourceManager:
    def __init__(self, config: Config, channel: Channel):
        self._sources: dict[str, Source] = {}
        self._errors: dict[str, str] = {}
        self._channel = channel
        self._init_sources(config)

    @property
    def sources(self) -> dict[str, Source]:
        return self._sources

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    def get_details(self) -> dict[str, dict]:
        return {name: source.details for name, source in self._sources.items()}

    def get_available(self) -> list[str]:
        return list(self._sources.keys())

    async def reinit(self, name: str, config: Config) -> Source | None:
        entry = SOURCES.get(name)
        if not entry:
            return None
        _, create = entry
        try:
            source = create(config)
            if source is None:
                self._sources.pop(name, None)
            else:
                if source.errors:
                    self._errors[name] = "; ".join(f"{k}: {v}" for k, v in source.errors.items())
                self._sources[name] = source
        except Exception as e:
            self._errors[name] = str(e)
            return None
        self._channel.publish(SourceChanged(source_name=name))
        return source

    async def remove(self, name: str) -> None:
        self._sources.pop(name, None)
        self._errors.pop(name, None)
        self._channel.publish(SourceChanged(source_name=name))

    def has_google_auth(self) -> bool:
        from ntrp.sources.google.auth import discover_gmail_tokens

        return len(discover_gmail_tokens()) > 0

    def _init_sources(self, config: Config) -> None:
        for name, (enabled, create) in SOURCES.items():
            if not enabled(config):
                continue
            try:
                source = create(config)
                if source is None:
                    continue
                if source.errors:
                    self._errors[name] = "; ".join(f"{k}: {v}" for k, v in source.errors.items())
                self._sources[name] = source
            except Exception as e:
                _logger.warning("Failed to init source %s: %s", name, e)
