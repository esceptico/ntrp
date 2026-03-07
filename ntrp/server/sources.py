from ntrp.channel import Channel
from ntrp.config import Config
from ntrp.events.internal import SourceChanged
from ntrp.logging import get_logger
from ntrp.sources.google.auth import discover_gmail_tokens
from ntrp.sources.registry import SOURCES

_logger = get_logger(__name__)


class SourceManager:
    def __init__(self, config: Config, channel: Channel):
        self._sources: dict[str, object] = {}
        self._errors: dict[str, str] = {}
        self._channel = channel
        self.sync(config)

    @property
    def sources(self) -> dict[str, object]:
        return dict(self._sources)

    @property
    def errors(self) -> dict[str, str]:
        errors = dict(self._errors)
        for name, source in self._sources.items():
            source_errors = getattr(source, "errors", None)
            if source_errors and name not in errors:
                errors[name] = "; ".join(f"{k}: {v}" for k, v in source_errors.items())
        return errors

    def get_details(self) -> dict[str, dict]:
        return {name: getattr(s, "details", {}) for name, s in self._sources.items()}

    def get_available(self) -> list[str]:
        return list(self._sources.keys())

    def _apply(self, name: str, config: Config) -> object | None:
        factory = SOURCES.get(name)
        if not factory:
            return None
        try:
            source = factory(config)
        except Exception as e:
            self._sources.pop(name, None)
            self._errors[name] = str(e)
            return None

        if source is None:
            self._sources.pop(name, None)
            self._errors.pop(name, None)
        else:
            self._sources[name] = source
            source_errors = getattr(source, "errors", None)
            if source_errors:
                self._errors[name] = "; ".join(f"{k}: {v}" for k, v in source_errors.items())
            else:
                self._errors.pop(name, None)
        return source

    def sync(self, config: Config) -> None:
        for name in SOURCES:
            self._apply(name, config)

    async def reinit(self, name: str, config: Config) -> object | None:
        source = self._apply(name, config)
        self._channel.publish(SourceChanged(source_name=name))
        return source

    async def remove(self, name: str) -> None:
        self._sources.pop(name, None)
        self._errors.pop(name, None)
        self._channel.publish(SourceChanged(source_name=name))

    def has_google_auth(self) -> bool:
        return len(discover_gmail_tokens()) > 0
