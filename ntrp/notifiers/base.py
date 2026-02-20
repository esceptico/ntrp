from abc import ABC, abstractmethod
from typing import Any, ClassVar


class Notifier(ABC):
    channel: ClassVar[str]

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict, runtime: Any) -> "Notifier": ...

    @abstractmethod
    async def send(self, subject: str, body: str) -> None: ...
