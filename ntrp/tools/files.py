import os
from typing import Any

from pydantic import BaseModel, Field

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.formatting import format_lines_with_pagination

READ_FILE_DESCRIPTION = (
    "Read content from a file. Use for code, configs, logs, etc. "
    "For large files, use offset and limit parameters to read in chunks. "
    "(For Obsidian notes, use read_note instead.)"
)


class ReadFileInput(BaseModel):
    path: str = Field(description="Path to the file (relative or absolute)")
    offset: int = Field(default=1, description="Line number to start from (1-based, default: 1)")
    limit: int = Field(default=500, description="Maximum lines to read (default: 500)")


class ReadFileTool(Tool):
    name = "read_file"
    description = READ_FILE_DESCRIPTION
    input_model = ReadFileInput

    def __init__(self, base_path: str | None = None):
        self.base_path = base_path or os.getcwd()

    async def execute(
        self, execution: Any, path: str = "", offset: int = 1, limit: int = 500, **kwargs: Any
    ) -> ToolResult:
        if not path:
            return ToolResult("Error: path is required", "Missing path")

        if not os.path.isabs(path):
            full_path = os.path.join(self.base_path, path)
        else:
            full_path = path

        full_path = os.path.normpath(full_path)

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
