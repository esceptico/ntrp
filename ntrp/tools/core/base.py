from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from ntrp.tools.core.context import ToolExecution


@dataclass
class ToolResult:
    content: str
    preview: str
    metadata: dict | None = None


def format_lines_with_pagination(
    content: str,
    offset: int = 1,
    limit: int = 500,
) -> str:
    """Format content with line numbers and pagination.

    Args:
        content: The text content to format
        offset: Line number to start from (1-based)
        limit: Maximum lines to return

    Returns:
        Formatted string with line numbers and header showing range
    """
    lines = content.split("\n")
    total_lines = len(lines)

    # Clamp offset
    offset = max(1, min(offset, total_lines))
    start_idx = offset - 1
    end_idx = min(start_idx + limit, total_lines)

    selected_lines = lines[start_idx:end_idx]

    # Format with line numbers
    output_lines = []
    for i, line in enumerate(selected_lines):
        line_num = start_idx + i + 1
        output_lines.append(f"{line_num:>6}|{line}")

    # Header with total
    header = f"[{total_lines} lines]"
    if start_idx > 0 or end_idx < total_lines:
        header = f"[{total_lines} lines, showing {offset}-{end_idx}]"

    return header + "\n" + "\n".join(output_lines)


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
