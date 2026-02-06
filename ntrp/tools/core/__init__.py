"""Core tool infrastructure - base classes, registry, context."""

from ntrp.tools.core.base import Tool, ToolResult, make_schema
from ntrp.tools.core.context import ApprovalResponse, PermissionDenied, ToolContext, ToolExecution
from ntrp.tools.core.formatting import format_lines_with_pagination
from ntrp.tools.core.registry import ToolRegistry

__all__ = [
    "ApprovalResponse",
    "PermissionDenied",
    "Tool",
    "ToolContext",
    "ToolExecution",
    "ToolRegistry",
    "ToolResult",
    "format_lines_with_pagination",
    "make_schema",
]
