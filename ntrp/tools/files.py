import os

from pydantic import BaseModel, Field

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.formatting import format_lines_with_pagination

READ_FILE_DESCRIPTION = (
    "Read content from a file. Use for code, configs, logs, etc. "
    "For large files, use offset and limit parameters to read in chunks."
)


_DEFAULT_OFFSET = 1
_DEFAULT_LINE_LIMIT = 500
_OFFLOAD_DIR = "/tmp/ntrp/"
_OFFLOAD_READ_LIMIT = 100


class ReadFileInput(BaseModel):
    path: str = Field(description="Path to the file (relative or absolute)")
    offset: int = Field(
        default=_DEFAULT_OFFSET, description=f"Line number to start from (1-based, default: {_DEFAULT_OFFSET})"
    )
    limit: int = Field(
        default=_DEFAULT_LINE_LIMIT, description=f"Maximum lines to read (default: {_DEFAULT_LINE_LIMIT})"
    )


async def read_file(execution: ToolExecution, args: ReadFileInput) -> ToolResult:
    path = os.path.expanduser(args.path)
    if not os.path.isabs(path):
        full_path = os.path.join(os.getcwd(), path)
    else:
        full_path = path

    full_path = os.path.normpath(full_path)
    offset = args.offset
    limit = args.limit

    # Guard: offloaded files with default params get capped to prevent
    # the agent from reading the entire offloaded result back into context
    is_offloaded = full_path.startswith(_OFFLOAD_DIR)
    if is_offloaded and offset == _DEFAULT_OFFSET and limit == _DEFAULT_LINE_LIMIT:
        limit = _OFFLOAD_READ_LIMIT

    if not os.path.exists(full_path):
        return ToolResult(
            content=f"File not found: {args.path}. Check the path or use bash(ls) to list directory.",
            preview="Not found",
        )

    if not os.path.isfile(full_path):
        return ToolResult(
            content=f"Path is a directory, not a file: {args.path}. Use bash(ls {args.path}) to list contents.",
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
            content=f"Permission denied: {args.path}. File may be protected or require elevated access.",
            preview="Denied",
        )
    except Exception as e:
        return ToolResult(content=f"Error reading file: {e}", preview="Read failed", is_error=True)


read_file_tool = tool(
    display_name="ReadFile",
    description=READ_FILE_DESCRIPTION,
    input_model=ReadFileInput,
    execute=read_file,
)
