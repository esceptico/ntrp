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


_DEFAULT_OFFSET = 1
_DEFAULT_LINE_LIMIT = 500


class ReadFileInput(BaseModel):
    path: str = Field(description="Path to the file (relative or absolute)")
    offset: int = Field(
        default=_DEFAULT_OFFSET, description=f"Line number to start from (1-based, default: {_DEFAULT_OFFSET})"
    )
    limit: int = Field(
        default=_DEFAULT_LINE_LIMIT, description=f"Maximum lines to read (default: {_DEFAULT_LINE_LIMIT})"
    )


class ReadFileTool(Tool):
    name = "read_file"
    display_name = "ReadFile"
    description = READ_FILE_DESCRIPTION
    input_model = ReadFileInput

    async def execute(
        self, execution: Any, path: str, offset: int = _DEFAULT_OFFSET, limit: int = _DEFAULT_LINE_LIMIT, **kwargs: Any
    ) -> ToolResult:
        if not os.path.isabs(path):
            full_path = os.path.join(os.getcwd(), path)
        else:
            full_path = path

        full_path = os.path.normpath(full_path)

        if not os.path.exists(full_path):
            return ToolResult(
                content=f"File not found: {path}. Check the path or use bash(ls) to list directory.",
                preview="Not found",
            )

        if not os.path.isfile(full_path):
            return ToolResult(
                content=f"Path is a directory, not a file: {path}. Use bash(ls {path}) to list contents.",
                preview="Not a file",
            )

        try:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            formatted = format_lines_with_pagination(content, offset, limit)
            lines = len(content.split("\n"))
            return ToolResult(content=formatted, preview=f"Read {lines} lines")

        except PermissionError:
            return ToolResult(
                content=f"Permission denied: {path}. File may be protected or require elevated access.",
                preview="Denied",
            )
        except Exception as e:
            return ToolResult(content=f"Error reading file: {e}", preview="Read failed", is_error=True)
