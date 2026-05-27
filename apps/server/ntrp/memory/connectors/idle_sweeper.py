import asyncio

from ntrp.logging import get_logger
from ntrp.memory.connectors._constants import IDLE_SWEEP_INTERVAL
from ntrp.memory.connectors.chat import ChatConnector

_logger = get_logger(__name__)


class IdleBufferSweeper:
    def __init__(self, connector: ChatConnector):
        self.connector = connector

    async def sweep_once(self) -> None:
        await self.connector.close_idle_buffers()

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
