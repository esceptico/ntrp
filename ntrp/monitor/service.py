from typing import Protocol, runtime_checkable

from ntrp.channel import Channel
from ntrp.logging import get_logger

_logger = get_logger(__name__)


@runtime_checkable
class MonitorProvider(Protocol):
    def start(self, channel: Channel) -> None: ...

    async def stop(self) -> None: ...


class Monitor:
    def __init__(self, channel: Channel):
        self.channel = channel
        self._providers: list[MonitorProvider] = []

    def register(self, provider: MonitorProvider) -> None:
        self._providers.append(provider)

    def start(self) -> None:
        if not self._providers:
            return
        for provider in self._providers:
            provider.start(self.channel)
        _logger.info("Monitor started (%d providers)", len(self._providers))

    async def stop(self) -> None:
        for provider in self._providers:
            await provider.stop()
        _logger.info("Monitor stopped")
