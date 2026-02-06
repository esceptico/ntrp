import os
from typing import Any

from ntrp.tools.core.base import Tool, ToolResult, make_schema
from ntrp.tools.core.formatting import format_lines_with_pagination


class ReadFileTool(Tool):
    """Read content from any file on the filesystem."""

    name = "read_file"
    description = (
        "Read content from a file. Use for code, configs, logs, etc. (For Obsidian notes, use read_note instead.)"
    )

    def __init__(self, base_path: str | None = None):
        """Initialize with optional base path for relative paths."""
        self.base_path = base_path or os.getcwd()

    @property
    def schema(self) -> dict:
        return make_schema(self.name, self.description, {
            "path": {
                "type": "string",
                "description": "Path to the file (relative or absolute)",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start from (1-based, default: 1)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum lines to read (default: 500)",
            },
        }, ["path"])

    async def execute(
        self, execution: Any, path: str = "", offset: int = 1, limit: int = 500, **kwargs: Any
    ) -> ToolResult:
        if not path:
            return ToolResult("Error: path is required", "Missing path")

        # Resolve path
        if not os.path.isabs(path):
            full_path = os.path.join(self.base_path, path)
        else:
            full_path = path

        # Normalize
        full_path = os.path.normpath(full_path)

        # Check exists
        if not os.path.exists(full_path):
            return ToolResult(f"File not found: {path}. Check the path or use bash(ls) to list directory.", "Not found")

        if not os.path.isfile(full_path):
            return ToolResult(
                f"Path is a directory, not a file: {path}. Use bash(ls {path}) to list contents.", "Not a file"
            )

        try:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            formatted = format_lines_with_pagination(content, offset, limit)
            lines = len(content.split("\n"))
            return ToolResult(formatted, f"Read {lines} lines")

        except PermissionError:
            return ToolResult(f"Permission denied: {path}. File may be protected or require elevated access.", "Denied")
        except Exception as e:
            return ToolResult(f"Error reading file: {e}", "Read failed")
