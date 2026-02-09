import difflib
import re
from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import (
    CONTENT_PREVIEW_LIMIT,
    DEFAULT_LIST_LIMIT,
    DEFAULT_READ_LINES,
    DIFF_PREVIEW_LINES,
    SNIPPET_TRUNCATE,
)
from ntrp.logging import get_logger
from ntrp.sources.base import NotesSource
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.formatting import format_lines_with_pagination
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


class NotesTool(Tool):
    name = "notes"
    description = NOTES_DESCRIPTION
    source_type = NotesSource
    input_model = NotesInput

    def __init__(self, source: NotesSource, search_index: Any | None = None):
        self.source = source
        self.search_index = search_index

    async def execute(
        self,
        execution: ToolExecution,
        query: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
        **kwargs: Any,
    ) -> ToolResult:
        if query:
            return await self._search(query, limit)
        return self._list(limit)

    def _list(self, limit: int) -> ToolResult:
        files_by_mtime = self.source.get_all_with_mtime()

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

    async def _search(self, query: str, limit: int) -> ToolResult:
        query = simplify_query(query)

        if self.search_index:
            try:
                results = await self.search_index.search(query, sources=["notes"], limit=limit)
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

        seen = set()
        results = []
        for path in self.source.search(query):
            if path in seen:
                continue
            seen.add(path)
            content = self.source.read(path) or ""
            snippet = truncate(content.replace("\n", " ").strip(), SNIPPET_TRUNCATE)
            title = path.split("/")[-1].replace(".md", "")
            results.append((title, path, snippet))
            if len(results) >= limit:
                break

        if not results:
            return ToolResult(content=f"No notes found for '{query}'", preview="0 notes")

        output = []
        for title, path, snippet in results:
            output.append(f"• {title}")
            output.append(f"  path: `{path}`")
            if snippet:
                output.append(f"  {snippet}")

        return ToolResult(content="\n".join(output), preview=f"{len(results)} notes")


class ReadNoteInput(BaseModel):
    path: str = Field(description="The relative path to the note file (e.g., 'folder/note.md')")
    offset: int | None = Field(default=None, description="Line number to start from (1-based, default: 1)")
    limit: int | None = Field(default=None, description=f"Maximum lines to read (default: {DEFAULT_READ_LINES})")


class ReadNoteTool(Tool):
    name = "read_note"
    description = READ_NOTE_DESCRIPTION
    source_type = NotesSource
    input_model = ReadNoteInput

    def __init__(self, source: NotesSource):
        self.source = source

    async def execute(
        self, execution: ToolExecution, path: str = "", offset: int = 1, limit: int = DEFAULT_READ_LINES, **kwargs: Any
    ) -> ToolResult:
        content = self.source.read(path)
        if content is None:
            return ToolResult(
                content=f"Note not found: {path}. Use notes() to see available notes.",
                preview="Not found",
            )

        formatted = format_lines_with_pagination(content, offset, limit)
        lines = len(content.split("\n"))

        return ToolResult(content=formatted, preview=f"Read {lines} lines")


class EditNoteInput(BaseModel):
    path: str = Field(description="Relative path to the note file")
    find: str = Field(description="Text to find (must match exactly)")
    replace: str = Field(description="Text to replace with")


class EditNoteTool(Tool):
    name = "edit_note"
    description = EDIT_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource
    input_model = EditNoteInput

    def __init__(self, source: NotesSource):
        self.source = source

    async def execute(
        self, execution: ToolExecution, path: str = "", find: str = "", replace: str = "", **kwargs: Any
    ) -> ToolResult:
        if not path or not find:
            return ToolResult(content="Error: path and find are required", preview="Missing fields", is_error=True)

        original = self.source.read(path)
        if original is None:
            return ToolResult(
                content=f"Note not found: {path}. Use notes() to find correct path.",
                preview="Not found",
            )

        if find not in original:
            return ToolResult(
                content=f"Text to replace not found in {path}. Read the note first to get exact text.",
                preview="Not found",
            )

        proposed = original.replace(find, replace, 1)
        diff = generate_diff(original, proposed, path)

        preview_lines = diff.split("\n")[:DIFF_PREVIEW_LINES]
        diff_preview = "\n".join(preview_lines)
        if len(diff.split("\n")) > DIFF_PREVIEW_LINES:
            diff_preview += "\n... (truncated)"

        await execution.require_approval(path, diff=diff_preview)

        success = self.source.write(path, proposed)
        if success:
            lines_changed = len([l for l in diff.split("\n") if l.startswith("+") or l.startswith("-")]) - 2
            return ToolResult(
                content=f"Applied edit to: {path}",
                preview="Edited",
                metadata={"diff": diff, "lines_changed": max(0, lines_changed)},
            )
        return ToolResult(content=f"Error writing to {path}", preview="Write failed", is_error=True)


class CreateNoteInput(BaseModel):
    path: str = Field(description="Relative path for the new note (e.g., 'projects/new-idea.md')")
    content: str = Field(description="Content for the new note")


class CreateNoteTool(Tool):
    name = "create_note"
    description = CREATE_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource
    input_model = CreateNoteInput

    def __init__(self, source: NotesSource):
        self.source = source

    async def execute(self, execution: ToolExecution, path: str = "", content: str = "", **kwargs: Any) -> ToolResult:
        if not path or not content:
            return ToolResult(content="Error: path and content are required", preview="Missing fields", is_error=True)

        if not path.endswith(".md"):
            path = path + ".md"

        if self.source.exists(path):
            return ToolResult(
                content=f"Note already exists: {path}. Use edit_note to modify or choose different path.",
                preview="Exists",
            )

        preview_content = content[:CONTENT_PREVIEW_LIMIT]
        if len(content) > CONTENT_PREVIEW_LIMIT:
            preview_content += "\n... (truncated)"

        await execution.require_approval(path, preview=preview_content)

        success = self.source.write(path, content)
        if success:
            return ToolResult(content=f"Created note: {path}", preview="Created")
        return ToolResult(content=f"Error creating {path}", preview="Create failed", is_error=True)


class DeleteNoteInput(BaseModel):
    path: str = Field(description="Relative path to the note file")


class DeleteNoteTool(Tool):
    name = "delete_note"
    description = DELETE_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource
    input_model = DeleteNoteInput

    def __init__(self, source: NotesSource):
        self.source = source

    async def execute(self, execution: ToolExecution, path: str = "", **kwargs: Any) -> ToolResult:
        if not path:
            return ToolResult(content="Error: path is required", preview="Missing path", is_error=True)

        original = self.source.read(path)
        if original is None:
            return ToolResult(
                content=f"Note not found: {path}. Use notes() to find correct path.",
                preview="Not found",
            )

        await execution.require_approval(path)

        success = self.source.delete(path)
        if success:
            return ToolResult(content=f"Deleted: {path}", preview="Deleted")
        return ToolResult(content=f"Error deleting {path}", preview="Delete failed", is_error=True)


class MoveNoteInput(BaseModel):
    path: str = Field(description="Current relative path to the note")
    new_path: str = Field(description="New relative path for the note")


class MoveNoteTool(Tool):
    name = "move_note"
    description = MOVE_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource
    input_model = MoveNoteInput

    def __init__(self, source: NotesSource):
        self.source = source

    async def execute(self, execution: ToolExecution, path: str = "", new_path: str = "", **kwargs: Any) -> ToolResult:
        if not path or not new_path:
            return ToolResult(content="Error: path and new_path are required", preview="Missing fields", is_error=True)

        if not new_path.endswith(".md"):
            new_path = new_path + ".md"

        if not self.source.exists(path):
            return ToolResult(
                content=f"Note not found: {path}. Use notes() to find correct path.",
                preview="Not found",
            )

        if self.source.exists(new_path):
            return ToolResult(
                content=f"Destination already exists: {new_path}. Choose different path or delete existing first.",
                preview="Exists",
            )

        await execution.require_approval(f"{path} → {new_path}")

        success = self.source.move(path, new_path)
        if success:
            return ToolResult(content=f"Moved: `{path}` → `{new_path}`", preview="Moved")
        return ToolResult(content=f"Error moving {path}", preview="Move failed", is_error=True)
