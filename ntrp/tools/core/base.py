from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from ntrp.tools.core.context import ToolExecution


def make_schema(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    schema: dict = {"name": name, "description": description}
    if properties:
        schema["parameters"] = {
            "type": "object",
            "properties": properties,
            "required": required or [],
        }
    return schema


@dataclass(frozen=True)
class ToolResult:
    content: str
    preview: str
    metadata: dict | None = None


class Tool(ABC):
    name: str
    description: str
    mutates: bool = False
    source_type: ClassVar[type | None] = None

    @property
    def available(self) -> bool:
        return True

    @property
    @abstractmethod
    def schema(self) -> dict: ...

    @abstractmethod
    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult: ...

    def to_dict(self) -> dict:
        return {
            "type": "function",
            "function": self.schema,
        }

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "mutates": self.mutates,
        }
