import asyncio
import difflib
import fnmatch
import os
from pathlib import Path

from pydantic import BaseModel, Field

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.formatting import format_lines_with_pagination
from ntrp.tools.core.types import ApprovalInfo, ToolAction, ToolPolicy, ToolScope

READ_FILE_DESCRIPTION = (
    "Read content from a file. Use for code, configs, logs, etc. "
    "For large files, use offset and limit parameters to read in chunks."
)
LIST_FILES_DESCRIPTION = "List files in a directory with compact type/size metadata."
FIND_FILES_DESCRIPTION = "Find files by glob pattern under a directory."
SEARCH_TEXT_DESCRIPTION = "Search local files for literal text."
WRITE_FILE_DESCRIPTION = "Write exact UTF-8 content to a file. Creates the file or replaces existing content."
EDIT_FILE_DESCRIPTION = "Edit a file by replacing one exact text block with another."


_DEFAULT_OFFSET = 1
_DEFAULT_LINE_LIMIT = 500
_OFFLOAD_DIR = "/tmp/ntrp/"
_OFFLOAD_READ_LIMIT = 100
_DEFAULT_ENTRY_LIMIT = 200
_DEFAULT_MATCH_LIMIT = 100


def _resolve_path(path: str) -> Path:
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (Path.cwd() / expanded).resolve()


def _size_label(path: Path) -> str:
    if path.is_dir():
        return "dir"
    size = path.stat().st_size
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _has_hidden_part(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return any(part.startswith(".") for part in relative.parts)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _unified_diff(path: Path, before: str, after: str) -> str | None:
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )
    return diff or None


# Each tool's filesystem-touching body runs through `asyncio.to_thread` so a
# slow read or a vault-wide search doesn't block the asyncio event loop —
# without this, automations and research agents (which lean heavily on
# read/search/find) would starve every other request on the server.


class ReadFileInput(BaseModel):
    path: str = Field(description="Path to the file (relative or absolute)")
    offset: int = Field(
        default=_DEFAULT_OFFSET, description=f"Line number to start from (1-based, default: {_DEFAULT_OFFSET})"
    )
    limit: int = Field(
        default=_DEFAULT_LINE_LIMIT, description=f"Maximum lines to read (default: {_DEFAULT_LINE_LIMIT})"
    )


def _read_file_sync(args: ReadFileInput) -> ToolResult:
    full_path = _resolve_path(args.path)
    offset = args.offset
    limit = args.limit

    # Guard: offloaded files with default params get capped to prevent
    # the agent from reading the entire offloaded result back into context
    is_offloaded = str(full_path).startswith(_OFFLOAD_DIR)
    if is_offloaded and offset == _DEFAULT_OFFSET and limit == _DEFAULT_LINE_LIMIT:
        limit = _OFFLOAD_READ_LIMIT

    if not full_path.exists():
        return ToolResult(
            content=f"File not found: {args.path}. Check the path or use list_files() to list the directory.",
            preview="Not found",
        )

    if not full_path.is_file():
        return ToolResult(
            content=f"Path is a directory, not a file: {args.path}. Use list_files(path={args.path!r}) to list contents.",
            preview="Not a file",
        )

    try:
        content = _read_text(full_path)
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


async def read_file(execution: ToolExecution, args: ReadFileInput) -> ToolResult:
    return await asyncio.to_thread(_read_file_sync, args)


class ListFilesInput(BaseModel):
    path: str = Field(default=".", description="Directory path to list.")
    limit: int = Field(default=_DEFAULT_ENTRY_LIMIT, ge=1, le=1000, description="Maximum entries to return.")
    include_hidden: bool = Field(default=False, description="Include dotfiles and dot-directories.")


def _list_files_sync(args: ListFilesInput) -> ToolResult:
    root = _resolve_path(args.path)
    if not root.exists():
        return ToolResult(content=f"Directory not found: {args.path}", preview="Not found", is_error=True)
    if not root.is_dir():
        return ToolResult(content=f"Path is not a directory: {args.path}", preview="Not a directory", is_error=True)

    try:
        entries = []
        for child in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if not args.include_hidden and child.name.startswith("."):
                continue
            suffix = "/" if child.is_dir() else ""
            entries.append(
                {
                    "name": f"{child.name}{suffix}",
                    "path": str(child),
                    "kind": "directory" if child.is_dir() else "file",
                    "size": _size_label(child),
                }
            )

        visible = entries[: args.limit]
        lines = [f"{item['name']:<48} {item['size']}" for item in visible]
        if len(entries) > args.limit:
            lines.append(f"... {len(entries) - args.limit} more")
        header = f"{root} ({len(entries)} entries)"
        return ToolResult(
            content=header + ("\n" + "\n".join(lines) if lines else "\n(empty)"),
            preview=f"{len(entries)} entries",
            data={"path": str(root), "entries": visible, "total": len(entries)},
        )
    except PermissionError:
        return ToolResult(content=f"Permission denied: {args.path}", preview="Denied", is_error=True)
    except OSError as e:
        return ToolResult(content=f"Error listing directory: {e}", preview="List failed", is_error=True)


async def list_files(execution: ToolExecution, args: ListFilesInput) -> ToolResult:
    return await asyncio.to_thread(_list_files_sync, args)


class FindFilesInput(BaseModel):
    path: str = Field(default=".", description="Directory path to search under.")
    pattern: str = Field(default="*", description="Glob pattern, for example '*.py' or '**/README.md'.")
    limit: int = Field(default=_DEFAULT_ENTRY_LIMIT, ge=1, le=1000, description="Maximum files to return.")
    include_hidden: bool = Field(default=False, description="Include dotfiles and dot-directories.")


def _find_files_sync(args: FindFilesInput) -> ToolResult:
    root = _resolve_path(args.path)
    if not root.exists():
        return ToolResult(content=f"Directory not found: {args.path}", preview="Not found", is_error=True)
    if not root.is_dir():
        return ToolResult(content=f"Path is not a directory: {args.path}", preview="Not a directory", is_error=True)

    try:
        matches = []
        for current_root, dir_names, file_names in os.walk(root):
            current = Path(current_root)
            if not args.include_hidden:
                dir_names[:] = [name for name in dir_names if not name.startswith(".")]
                file_names = [name for name in file_names if not name.startswith(".")]
            dir_names.sort(key=str.lower)
            for name in sorted(file_names, key=str.lower):
                path = current / name
                relative = path.relative_to(root).as_posix()
                if not fnmatch.fnmatch(relative, args.pattern) and not fnmatch.fnmatch(name, args.pattern):
                    continue
                matches.append({"path": str(path), "relative_path": relative, "size": _size_label(path)})
                if len(matches) >= args.limit:
                    break
            if len(matches) >= args.limit:
                break

        lines = [f"{item['relative_path']:<72} {item['size']}" for item in matches]
        if not lines:
            lines = ["No files found."]
        return ToolResult(
            content=f"{root} / {args.pattern}\n" + "\n".join(lines),
            preview=f"{len(matches)} files",
            data={"path": str(root), "pattern": args.pattern, "matches": matches},
        )
    except PermissionError:
        return ToolResult(content=f"Permission denied: {args.path}", preview="Denied", is_error=True)
    except OSError as e:
        return ToolResult(content=f"Error finding files: {e}", preview="Find failed", is_error=True)


async def find_files(execution: ToolExecution, args: FindFilesInput) -> ToolResult:
    return await asyncio.to_thread(_find_files_sync, args)


class SearchTextInput(BaseModel):
    query: str = Field(min_length=1, description="Literal text to search for.")
    path: str = Field(default=".", description="File or directory path to search.")
    file_glob: str | None = Field(default=None, description="Optional file glob, for example '*.py'.")
    limit: int = Field(default=_DEFAULT_MATCH_LIMIT, ge=1, le=1000, description="Maximum matches to return.")


def _format_match(match: dict) -> str:
    return f"{match['relative_path']}:{match['line']}:{match['column']}: {match['text']}"


def _search_text_sync(args: SearchTextInput) -> ToolResult:
    root = _resolve_path(args.path)
    if not root.exists():
        return ToolResult(content=f"Path not found: {args.path}", preview="Not found", is_error=True)

    try:
        return _do_search(root, args)
    except OSError as e:
        return ToolResult(content=f"Error searching files: {e}", preview="Search failed", is_error=True)


def _do_search(root: Path, args: SearchTextInput) -> ToolResult:
    paths = (root,) if root.is_file() else root.rglob(args.file_glob or "*")
    matches = []
    for path in paths:
        if not path.is_file():
            continue
        if root.is_dir() and _has_hidden_part(path, root):
            continue
        try:
            for line_no, line in enumerate(_read_text(path).splitlines(), start=1):
                column = line.find(args.query)
                if column == -1:
                    continue
                try:
                    relative = path.relative_to(root).as_posix()
                except ValueError:
                    relative = str(path)
                matches.append(
                    {
                        "path": str(path),
                        "relative_path": relative,
                        "line": line_no,
                        "column": column + 1,
                        "text": line,
                    }
                )
                if len(matches) >= args.limit:
                    break
        except UnicodeDecodeError:
            continue
        if len(matches) >= args.limit:
            break

    if not matches:
        return ToolResult(
            content=f"No matches for {args.query!r} under {root}.",
            preview="0 matches",
            data={"path": str(root), "query": args.query, "matches": []},
        )
    return ToolResult(
        content="\n".join(_format_match(match) for match in matches),
        preview=f"{len(matches)} matches",
        data={"path": str(root), "query": args.query, "matches": matches},
    )


async def search_text(execution: ToolExecution, args: SearchTextInput) -> ToolResult:
    return await asyncio.to_thread(_search_text_sync, args)


class WriteFileInput(BaseModel):
    path: str = Field(description="Path to write.")
    content: str = Field(description="Full file content to write.")


def _approve_write_file_sync(args: WriteFileInput) -> ApprovalInfo | None:
    path = _resolve_path(args.path)
    if path.exists() and path.is_dir():
        return None
    if not path.parent.exists():
        return None
    before = _read_text(path) if path.exists() and path.is_file() else ""
    diff = _unified_diff(path, before, args.content)
    action = "Replace" if path.exists() else "Create"
    return ApprovalInfo(description=f"{action} {path}", preview=args.content[:500], diff=diff)


async def approve_write_file(execution: ToolExecution, args: WriteFileInput) -> ApprovalInfo | None:
    return await asyncio.to_thread(_approve_write_file_sync, args)


def _write_file_sync(args: WriteFileInput) -> ToolResult:
    path = _resolve_path(args.path)
    if path.exists() and path.is_dir():
        return ToolResult(content=f"Path is a directory: {args.path}", preview="Is directory", is_error=True)
    if not path.parent.exists():
        return ToolResult(content=f"Parent directory does not exist: {path.parent}", preview="No parent", is_error=True)

    try:
        path.write_text(args.content, encoding="utf-8")
    except PermissionError:
        return ToolResult(content=f"Permission denied: {args.path}", preview="Denied", is_error=True)
    except OSError as e:
        return ToolResult(content=f"Error writing file: {e}", preview="Write failed", is_error=True)

    lines = args.content.count("\n") + 1 if args.content else 0
    return ToolResult(
        content=f"Wrote {path} ({lines} lines).",
        preview=f"Wrote {lines} lines",
        data={"path": str(path), "lines": lines},
    )


async def write_file(execution: ToolExecution, args: WriteFileInput) -> ToolResult:
    return await asyncio.to_thread(_write_file_sync, args)


class EditFileInput(BaseModel):
    path: str = Field(description="Path to edit.")
    old_text: str = Field(min_length=1, description="Exact existing text block to replace. Must match once.")
    new_text: str = Field(description="Replacement text.")


def _approve_edit_file_sync(args: EditFileInput) -> ApprovalInfo | None:
    path = _resolve_path(args.path)
    if not path.exists() or not path.is_file():
        return None
    before = _read_text(path)
    if before.count(args.old_text) != 1:
        return None
    after = before.replace(args.old_text, args.new_text, 1)
    return ApprovalInfo(
        description=f"Edit {path}", preview=args.new_text[:500], diff=_unified_diff(path, before, after)
    )


async def approve_edit_file(execution: ToolExecution, args: EditFileInput) -> ApprovalInfo | None:
    return await asyncio.to_thread(_approve_edit_file_sync, args)


def _edit_file_sync(args: EditFileInput) -> ToolResult:
    path = _resolve_path(args.path)
    if not path.exists():
        return ToolResult(content=f"File not found: {args.path}", preview="Not found", is_error=True)
    if not path.is_file():
        return ToolResult(content=f"Path is not a file: {args.path}", preview="Not a file", is_error=True)

    try:
        before = _read_text(path)
    except PermissionError:
        return ToolResult(content=f"Permission denied: {args.path}", preview="Denied", is_error=True)
    count = before.count(args.old_text)
    if count == 0:
        return ToolResult(
            content="Text block not found. Read the file and include more exact context.",
            preview="No match",
            is_error=True,
        )
    if count > 1:
        return ToolResult(
            content=f"Text block matched {count} times. Include a larger exact block so the edit is unique.",
            preview="Ambiguous",
            is_error=True,
        )

    after = before.replace(args.old_text, args.new_text, 1)
    try:
        path.write_text(after, encoding="utf-8")
    except PermissionError:
        return ToolResult(content=f"Permission denied: {args.path}", preview="Denied", is_error=True)
    except OSError as e:
        return ToolResult(content=f"Error editing file: {e}", preview="Edit failed", is_error=True)

    return ToolResult(content=f"Edited {path}.", preview="Edited", data={"path": str(path)})


async def edit_file(execution: ToolExecution, args: EditFileInput) -> ToolResult:
    return await asyncio.to_thread(_edit_file_sync, args)


read_file_tool = tool(
    display_name="ReadFile",
    description=READ_FILE_DESCRIPTION,
    input_model=ReadFileInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=read_file,
)

list_files_tool = tool(
    display_name="ListFiles",
    description=LIST_FILES_DESCRIPTION,
    input_model=ListFilesInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=list_files,
)

find_files_tool = tool(
    display_name="FindFiles",
    description=FIND_FILES_DESCRIPTION,
    input_model=FindFilesInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=find_files,
)

search_text_tool = tool(
    display_name="SearchText",
    description=SEARCH_TEXT_DESCRIPTION,
    input_model=SearchTextInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=search_text,
)

write_file_tool = tool(
    display_name="WriteFile",
    description=WRITE_FILE_DESCRIPTION,
    input_model=WriteFileInput,
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL, requires_approval=True),
    approval=approve_write_file,
    execute=write_file,
)

edit_file_tool = tool(
    display_name="EditFile",
    description=EDIT_FILE_DESCRIPTION,
    input_model=EditFileInput,
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL, requires_approval=True),
    approval=approve_edit_file,
    execute=edit_file,
)
