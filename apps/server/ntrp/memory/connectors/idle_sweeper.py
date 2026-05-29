import asyncio
from collections.abc import Callable

from ntrp.logging import get_logger
from ntrp.memory.connectors._constants import IDLE_SWEEP_INTERVAL
from ntrp.memory.connectors.base import BufferingConnector

_logger = get_logger(__name__)


class IdleBufferSweeper:
    def __init__(self, get_connectors: Callable[[], list[BufferingConnector]]):
        self.get_connectors = get_connectors

    async def sweep_once(self) -> None:
        for connector in self.get_connectors():
            await connector.close_idle_buffers()

    async def run_loop(self) -> None:
        try:
            while True:
                try:
                    await self.sweep_once()
                except Exception:
                    _logger.warning("Idle memory buffer sweep failed", exc_info=True)
                await asyncio.sleep(IDLE_SWEEP_INTERVAL.total_seconds())
        except asyncio.CancelledError:
            raise
