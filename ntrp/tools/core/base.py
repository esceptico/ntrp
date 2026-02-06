from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from ntrp.tools.core.context import ToolExecution


def make_schema(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


@dataclass
class ToolResult:
    content: str
    preview: str
    metadata: dict | None = None


class Tool(ABC):
    """Base class for all tools."""

    name: str
    description: str
    mutates: bool = False
    source_type: ClassVar[type | None] = None

    @property
    def available(self) -> bool:
        """Check if tool is available (has required dependencies).

        Override in subclasses to check if required sources exist.
        """
        return True

    @property
    @abstractmethod
    def schema(self) -> dict:
        """Return OpenAI function schema for this tool."""
        ...

    @abstractmethod
    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        """Execute the tool and return result.

        Args:
            execution: Per-tool execution context with permission handling
            **kwargs: Tool-specific arguments
        """
        ...

    def to_dict(self) -> dict:
        return {
            "type": "function",
            "function": self.schema,
        }

    def get_metadata(self) -> dict:
        """Get tool metadata for the API."""
        return {
            "name": self.name,
            "description": self.description,
            "mutates": self.mutates,
        }
