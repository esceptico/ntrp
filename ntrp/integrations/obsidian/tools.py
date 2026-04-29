import asyncio
import difflib
import re

from pydantic import BaseModel, Field

from ntrp.constants import (
    CONTENT_PREVIEW_LIMIT,
    DEFAULT_LIST_LIMIT,
    DEFAULT_READ_LINES,
    DIFF_PREVIEW_LINES,
    SNIPPET_TRUNCATE,
)
from ntrp.integrations.obsidian.client import ObsidianClient
from ntrp.logging import get_logger
from ntrp.search.index import SearchIndex
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.formatting import format_lines_with_pagination
from ntrp.tools.core.types import ApprovalInfo
from ntrp.utils import truncate

_logger = get_logger(__name__)


READ_NOTE_DESCRIPTION = (
    "Read a note by path. Use notes(query) first to find paths. Supports offset/limit for large notes."
)

EDIT_NOTE_DESCRIPTION = """Edit a note by find-and-replace. Requires approval. Always read_note() first.
find text must match exactly. For large changes, use multiple small edits."""

CREATE_NOTE_DESCRIPTION = """Create a new note. Requires approval. Search first to avoid duplicates.
Check for templates in vault. .md added automatically. Fails if note exists."""

DELETE_NOTE_DESCRIPTION = "Permanently delete a note. Requires approval. Always read_note() first to confirm."


def simplify_query(query: str) -> str:
    simplified = re.sub(r"\s+OR\s+", " ", query, flags=re.IGNORECASE)
    simplified = re.sub(r"\s+AND\s+", " ", simplified, flags=re.IGNORECASE)
    simplified = simplified.replace('"', "").replace("'", "")
    simplified = simplified.replace("(", "").replace(")", "")
    simplified = re.sub(r"\s+", " ", simplified).strip()

    words = simplified.split()
    if len(words) > 6:
        simplified = " ".join(words[:5])

    return simplified


def generate_diff(original: str, proposed: str, path: str) -> str:
    original_lines = original.splitlines(keepends=True)
    proposed_lines = proposed.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        proposed_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "".join(diff)


NOTES_DESCRIPTION = """Browse or search notes in the Obsidian vault.

Without query: lists all notes sorted by most recently modified. Use limit to control how many.
With query: searches note content. Use simple keywords (2-4 words, no boolean operators).

Use read_note(path) to get full content after finding notes."""

MOVE_NOTE_DESCRIPTION = "Move or rename a note in the vault. User must approve the operation."


class NotesInput(BaseModel):
    query: str | None = Field(default=None, description="Search query. Omit to list recent notes.")
    limit: int | None = Field(default=None, description=f"Maximum results (default: {DEFAULT_LIST_LIMIT})")


async def _list_notes(source: ObsidianClient, limit: int) -> ToolResult:
    files_by_mtime = await asyncio.to_thread(source.get_all_with_mtime)

    sorted_files = sorted(
        files_by_mtime.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    total = len(sorted_files)
    showing = min(limit, total)

    formatted_names = [f"`{name}`" for name, _mtime in sorted_files[:limit]]

    header = f"{showing} of {total} notes:" if showing < total else f"{total} notes:"
    content = f"{header}\n" + "\n".join(formatted_names)

    return ToolResult(content=content, preview=f"{showing} notes")


async def _search_notes(
    source: ObsidianClient, query: str, limit: int, search_index: SearchIndex | None = None
) -> ToolResult:
    query = simplify_query(query)

    if search_index:
        try:
            results = await search_index.search(query, sources=["notes"], limit=limit)
            if results:
                output = []
                for item in results:
                    output.append(f"• {item.title}")
                    output.append(f"  path: `{item.source_id}`")
                    if item.snippet:
                        output.append(f"  {truncate(item.snippet, SNIPPET_TRUNCATE)}")
                return ToolResult(content="\n".join(output), preview=f"{len(results)} notes")
        except Exception as e:
            _logger.warning("Hybrid search failed, falling back to text search: %s", e)

    def _text_search():
        seen = set()
        results = []
        for path in source.search(query):
            if path in seen:
                continue
            seen.add(path)
            content = source.read(path) or ""
            snippet = truncate(content.replace("\n", " ").strip(), SNIPPET_TRUNCATE)
            title = path.split("/")[-1].replace(".md", "")
            results.append((title, path, snippet))
            if len(results) >= limit:
                break
        return results

    results = await asyncio.to_thread(_text_search)

    if not results:
        return ToolResult(content=f"No notes found for '{query}'", preview="0 notes")

    output = []
    for title, path, snippet in results:
        output.append(f"• {title}")
        output.append(f"  path: `{path}`")
        if snippet:
            output.append(f"  {snippet}")

    return ToolResult(content="\n".join(output), preview=f"{len(results)} notes")


async def notes(execution: ToolExecution, args: NotesInput) -> ToolResult:
    source = execution.ctx.get_client("notes", ObsidianClient)
    limit = args.limit or DEFAULT_LIST_LIMIT
    if args.query:
        search_index = execution.ctx.services.get("search_index")
        return await _search_notes(source, args.query, limit, search_index)
    return await _list_notes(source, limit)


class ReadNoteInput(BaseModel):
    path: str = Field(description="The relative path to the note file (e.g., 'folder/note.md')")
    offset: int | None = Field(default=None, description="Line number to start from (1-based, default: 1)")
    limit: int | None = Field(default=None, description=f"Maximum lines to read (default: {DEFAULT_READ_LINES})")


async def read_note(execution: ToolExecution, args: ReadNoteInput) -> ToolResult:
    source = execution.ctx.get_client("notes", ObsidianClient)
    offset = args.offset or 1
    limit = args.limit or DEFAULT_READ_LINES
    content = await asyncio.to_thread(source.read, args.path)
    if content is None:
        return ToolResult(
            content=f"Note not found: {args.path}. Use notes() to see available notes.",
            preview="Not found",
        )

    formatted = format_lines_with_pagination(content, offset, limit)
    lines = len(content.split("\n"))

    return ToolResult(content=formatted, preview=f"Read {lines} lines")


class EditNoteInput(BaseModel):
    path: str = Field(description="Relative path to the note file")
    find: str = Field(description="Text to find (must match exactly)")
    replace: str = Field(description="Text to replace with")


async def approve_edit_note(execution: ToolExecution, args: EditNoteInput) -> ApprovalInfo | None:
    source = execution.ctx.get_client("notes", ObsidianClient)
    original = source.read(args.path)
    if original is None or args.find not in original:
        return None
    proposed = original.replace(args.find, args.replace, 1)
    diff = generate_diff(original, proposed, args.path)
    preview_lines = diff.split("\n")[:DIFF_PREVIEW_LINES]
    diff_preview = "\n".join(preview_lines)
    if len(diff.split("\n")) > DIFF_PREVIEW_LINES:
        diff_preview += "\n... (truncated)"
    return ApprovalInfo(description=args.path, preview=None, diff=diff_preview)


async def edit_note(execution: ToolExecution, args: EditNoteInput) -> ToolResult:
    source = execution.ctx.get_client("notes", ObsidianClient)
    original = source.read(args.path)
    if original is None:
        return ToolResult(
            content=f"Note not found: {args.path}. Use notes() to find correct path.",
            preview="Not found",
        )

    if args.find not in original:
        return ToolResult(
            content=f"Text to replace not found in {args.path}. Read the note first to get exact text.",
            preview="Not found",
        )

    proposed = original.replace(args.find, args.replace, 1)
    diff = generate_diff(original, proposed, args.path)

    success = source.write(args.path, proposed)
    if success:
        lines_changed = len([line for line in diff.split("\n") if line.startswith("+") or line.startswith("-")]) - 2
        return ToolResult(
            content=f"Applied edit to: {args.path}",
            preview="Edited",
            data={
                "diff": {"path": args.path, "before": original, "after": proposed},
                "lines_changed": max(0, lines_changed),
            },
        )
    return ToolResult(content=f"Error writing to {args.path}", preview="Write failed", is_error=True)


class CreateNoteInput(BaseModel):
    path: str = Field(description="Relative path for the new note (e.g., 'projects/new-idea.md')")
    content: str = Field(description="Content for the new note")


async def approve_create_note(execution: ToolExecution, args: CreateNoteInput) -> ApprovalInfo | None:
    source = execution.ctx.get_client("notes", ObsidianClient)
    path = args.path if args.path.endswith(".md") else args.path + ".md"
    if source.exists(path):
        return None
    preview_content = args.content[:CONTENT_PREVIEW_LIMIT]
    if len(args.content) > CONTENT_PREVIEW_LIMIT:
        preview_content += "\n... (truncated)"
    return ApprovalInfo(description=path, preview=preview_content, diff=None)


async def create_note(execution: ToolExecution, args: CreateNoteInput) -> ToolResult:
    source = execution.ctx.get_client("notes", ObsidianClient)
    path = args.path if args.path.endswith(".md") else args.path + ".md"

    if source.exists(path):
        return ToolResult(
            content=f"Note already exists: {path}. Use edit_note to modify or choose different path.",
            preview="Exists",
        )

    success = source.write(path, args.content)
    if success:
        return ToolResult(content=f"Created note: {path}", preview="Created")
    return ToolResult(content=f"Error creating {path}", preview="Create failed", is_error=True)


class DeleteNoteInput(BaseModel):
    path: str = Field(description="Relative path to the note file")


async def approve_delete_note(execution: ToolExecution, args: DeleteNoteInput) -> ApprovalInfo | None:
    source = execution.ctx.get_client("notes", ObsidianClient)
    if source.read(args.path) is None:
        return None
    return ApprovalInfo(description=args.path, preview=None, diff=None)


async def delete_note(execution: ToolExecution, args: DeleteNoteInput) -> ToolResult:
    source = execution.ctx.get_client("notes", ObsidianClient)
    original = source.read(args.path)
    if original is None:
        return ToolResult(
            content=f"Note not found: {args.path}. Use notes() to find correct path.",
            preview="Not found",
        )

    success = source.delete(args.path)
    if success:
        return ToolResult(content=f"Deleted: {args.path}", preview="Deleted")
    return ToolResult(content=f"Error deleting {args.path}", preview="Delete failed", is_error=True)


class MoveNoteInput(BaseModel):
    path: str = Field(description="Current relative path to the note")
    new_path: str = Field(description="New relative path for the note")


async def approve_move_note(execution: ToolExecution, args: MoveNoteInput) -> ApprovalInfo | None:
    source = execution.ctx.get_client("notes", ObsidianClient)
    if not source.exists(args.path):
        return None
    return ApprovalInfo(description=f"{args.path} → {args.new_path}", preview=None, diff=None)


async def move_note(execution: ToolExecution, args: MoveNoteInput) -> ToolResult:
    source = execution.ctx.get_client("notes", ObsidianClient)
    new_path = args.new_path if args.new_path.endswith(".md") else args.new_path + ".md"

    if not source.exists(args.path):
        return ToolResult(
            content=f"Note not found: {args.path}. Use notes() to find correct path.",
            preview="Not found",
        )

    if source.exists(new_path):
        return ToolResult(
            content=f"Destination already exists: {new_path}. Choose different path or delete existing first.",
            preview="Exists",
        )

    success = source.move(args.path, new_path)
    if success:
        return ToolResult(content=f"Moved: `{args.path}` → `{new_path}`", preview="Moved")
    return ToolResult(content=f"Error moving {args.path}", preview="Move failed", is_error=True)


notes_tool = tool(
    display_name="Notes",
    description=NOTES_DESCRIPTION,
    input_model=NotesInput,
    requires={"notes"},
    execute=notes,
)

read_note_tool = tool(
    display_name="ReadNote",
    description=READ_NOTE_DESCRIPTION,
    input_model=ReadNoteInput,
    requires={"notes"},
    execute=read_note,
)

edit_note_tool = tool(
    display_name="EditNote",
    description=EDIT_NOTE_DESCRIPTION,
    input_model=EditNoteInput,
    mutates=True,
    requires={"notes"},
    approval=approve_edit_note,
    execute=edit_note,
)

create_note_tool = tool(
    display_name="CreateNote",
    description=CREATE_NOTE_DESCRIPTION,
    input_model=CreateNoteInput,
    mutates=True,
    requires={"notes"},
    approval=approve_create_note,
    execute=create_note,
)

delete_note_tool = tool(
    display_name="DeleteNote",
    description=DELETE_NOTE_DESCRIPTION,
    input_model=DeleteNoteInput,
    mutates=True,
    requires={"notes"},
    approval=approve_delete_note,
    execute=delete_note,
)

move_note_tool = tool(
    display_name="MoveNote",
    description=MOVE_NOTE_DESCRIPTION,
    input_model=MoveNoteInput,
    mutates=True,
    requires={"notes"},
    approval=approve_move_note,
    execute=move_note,
)
