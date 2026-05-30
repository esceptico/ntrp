"""Memory service shell for the memory_items pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ntrp.memory.runtime import MemoryDatabase

if TYPE_CHECKING:
    from ntrp.memory.connectors.base import BufferingConnector
    from ntrp.memory.connectors.chat import ChatConnector


class MemoryService:
    def __init__(self, memory: MemoryDatabase):
        self.memory = memory
        self.chat_connector: ChatConnector | None = None
        self.connectors: list[BufferingConnector] = []

    def register_connector(self, connector: BufferingConnector) -> None:
        self.connectors.append(connector)
