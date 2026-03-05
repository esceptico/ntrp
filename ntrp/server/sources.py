from typing import cast

from ntrp.channel import Channel
from ntrp.config import Config
from ntrp.events.internal import SourceChanged
from ntrp.logging import get_logger
from ntrp.sources.base import Source
from ntrp.sources.google.auth import discover_gmail_tokens
from ntrp.sources.registry import SOURCES

_logger = get_logger(__name__)


class SourceManager:
    def __init__(self, target: dict[str, object], config: Config, channel: Channel):
        self._target = target
        self._source_names: set[str] = set()
        self._errors: dict[str, str] = {}
        self._channel = channel
        self._init_sources(config)

    @property
    def sources(self) -> dict[str, Source]:
        return {name: cast("Source", self._target[name]) for name in self._source_names if name in self._target}

    @property
    def errors(self) -> dict[str, str]:
        errors = dict(self._errors)
        for name, source in self.sources.items():
            if source.errors and name not in errors:
                errors[name] = "; ".join(f"{k}: {v}" for k, v in source.errors.items())
        return errors

    def get_details(self) -> dict[str, dict]:
        return {name: s.details for name, s in self.sources.items()}

    def get_available(self) -> list[str]:
        return [name for name in self._source_names if name in self._target]

    def sync(self, config: Config) -> None:
        for name, factory in SOURCES.items():
            try:
                source = factory(config)
            except Exception as e:
                self._target.pop(name, None)
                self._source_names.discard(name)
                self._errors[name] = str(e)
                continue

            if source is None:
                self._target.pop(name, None)
                self._source_names.discard(name)
                self._errors.pop(name, None)
            else:
                if source.errors:
                    self._errors[name] = "; ".join(f"{k}: {v}" for k, v in source.errors.items())
                else:
                    self._errors.pop(name, None)
                self._target[name] = source
                self._source_names.add(name)

    async def reinit(self, name: str, config: Config) -> Source | None:
        factory = SOURCES.get(name)
        if not factory:
            return None
        try:
            source = factory(config)
            if source is None:
                self._target.pop(name, None)
                self._source_names.discard(name)
            else:
                if source.errors:
                    self._errors[name] = "; ".join(f"{k}: {v}" for k, v in source.errors.items())
                else:
                    self._errors.pop(name, None)
                self._target[name] = source
                self._source_names.add(name)
        except Exception as e:
            self._target.pop(name, None)
            self._source_names.discard(name)
            self._errors[name] = str(e)
            return None
        self._channel.publish(SourceChanged(source_name=name))
        return source

    async def remove(self, name: str) -> None:
        self._target.pop(name, None)
        self._source_names.discard(name)
        self._errors.pop(name, None)
        self._channel.publish(SourceChanged(source_name=name))

    def has_google_auth(self) -> bool:
        return len(discover_gmail_tokens()) > 0

    def _init_sources(self, config: Config) -> None:
        for name, factory in SOURCES.items():
            try:
                source = factory(config)
                if source is None:
                    continue
                if source.errors:
                    self._errors[name] = "; ".join(f"{k}: {v}" for k, v in source.errors.items())
                self._target[name] = source
                self._source_names.add(name)
            except Exception as e:
                _logger.warning("Failed to init source %s: %s", name, e)
