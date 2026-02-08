from dataclasses import dataclass
from typing import Any

from ntrp.bus import EventBus
from ntrp.config import Config
from ntrp.logging import get_logger
from ntrp.sources.registry import SOURCES

_logger = get_logger(__name__)


@dataclass
class SourceChanged:
    source_name: str


class SourceManager:
    def __init__(self, config: Config, bus: EventBus):
        self._sources: dict[str, Any] = {}
        self._errors: dict[str, str] = {}
        self._bus = bus
        self._init_sources(config)

    @property
    def sources(self) -> dict[str, Any]:
        return self._sources

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    def get_details(self) -> dict[str, dict]:
        return {name: source.details for name, source in self._sources.items()}

    def get_available(self) -> list[str]:
        return list(self._sources.keys())

    async def reinit(self, name: str, config: Config) -> Any | None:
        spec = SOURCES.get(name)
        if not spec:
            return None
        try:
            source = spec.create(config)
            if source is None:
                self._sources.pop(name, None)
            else:
                if source.errors:
                    self._errors[name] = "; ".join(
                        f"{k}: {v}" for k, v in source.errors.items()
                    )
                self._sources[name] = source
        except Exception as e:
            self._errors[name] = str(e)
            return None
        await self._bus.publish(SourceChanged(source_name=name))
        return source

    async def remove(self, name: str) -> None:
        self._sources.pop(name, None)
        self._errors.pop(name, None)
        await self._bus.publish(SourceChanged(source_name=name))

    def _init_sources(self, config: Config) -> None:
        for name, spec in SOURCES.items():
            if not spec.enabled(config):
                continue
            try:
                source = spec.create(config)
                if source is None:
                    continue
                if source.errors:
                    self._errors[name] = "; ".join(
                        f"{k}: {v}" for k, v in source.errors.items()
                    )
                self._sources[name] = source
            except Exception as e:
                _logger.warning("Failed to init source %s: %s", name, e)
