import difflib
import re
from typing import Any

from ntrp.constants import (
    CONTENT_PREVIEW_LIMIT,
    DEFAULT_LIST_LIMIT,
    DEFAULT_READ_LINES,
    DIFF_PREVIEW_LINES,
    SNIPPET_TRUNCATE,
)
from ntrp.logging import get_logger
from ntrp.sources.base import NotesSource
from ntrp.tools.core.base import Tool, ToolResult, make_schema
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.formatting import format_lines_with_pagination
from ntrp.utils import truncate

logger = get_logger(__name__)


READ_NOTE_DESCRIPTION = "Read a note by path. Use search_notes() first to find paths. Supports offset/limit for large notes."

EDIT_NOTE_DESCRIPTION = """Edit a note by find-and-replace. Requires approval. Always read_note() first.
find text must match exactly. For large changes, use multiple small edits."""

CREATE_NOTE_DESCRIPTION = """Create a new note. Requires approval. Search first to avoid duplicates.
Check for templates in vault. .md added automatically. Fails if note exists."""

DELETE_NOTE_DESCRIPTION = "Permanently delete a note. Requires approval. Always read_note() first to confirm."


def simplify_query(query: str) -> str:
    """Strip boolean operators, quotes, parentheses from complex queries."""
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
    """Generate a unified diff between original and proposed content."""
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


LIST_NOTES_DESCRIPTION = "List note files in the Obsidian vault, sorted by most recently modified."

MOVE_NOTE_DESCRIPTION = "Move or rename a note in the vault. User must approve the operation."

SEARCH_NOTES_DESCRIPTION = """Search notes by content.

QUERY FORMAT:
- Use natural language: "job applications", "MATS program"
- Avoid boolean operators: no AND, OR, quotes
- Keep queries simple: 2-4 words work best

After finding notes, use read_note(path) to get full content."""


class ListNotesTool(Tool):
    """List all notes in the vault."""

    name = "list_notes"
    description = LIST_NOTES_DESCRIPTION
    source_type = NotesSource

    def __init__(self, source: NotesSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "limit": {
                    "type": "integer",
                    "description": f"Maximum notes to return (default: {DEFAULT_LIST_LIMIT})",
                },
            },
        )

    async def execute(
        self,
        execution: ToolExecution,
        limit: int = DEFAULT_LIST_LIMIT,
        **kwargs: Any,
    ) -> ToolResult:
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

        return ToolResult(content, f"{showing} notes")


class ReadNoteTool(Tool):
    """Read a single note."""

    name = "read_note"
    description = READ_NOTE_DESCRIPTION
    source_type = NotesSource

    def __init__(self, source: NotesSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "path": {
                    "type": "string",
                    "description": "The relative path to the note file (e.g., 'folder/note.md')",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start from (1-based, default: 1)",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Maximum lines to read (default: {DEFAULT_READ_LINES})",
                },
            },
            ["path"],
        )

    async def execute(
        self, execution: ToolExecution, path: str = "", offset: int = 1, limit: int = DEFAULT_READ_LINES, **kwargs: Any
    ) -> ToolResult:
        content = self.source.read(path)
        if content is None:
            return ToolResult(f"Note not found: {path}. Use list_notes to see available notes.", "Not found")

        formatted = format_lines_with_pagination(content, offset, limit)
        lines = len(content.split("\n"))

        return ToolResult(formatted, f"Read {lines} lines")


class EditNoteTool(Tool):
    """Propose an edit to a note. Edit must be approved by user."""

    name = "edit_note"
    description = EDIT_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource

    def __init__(self, source: NotesSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "path": {
                    "type": "string",
                    "description": "Relative path to the note file",
                },
                "find": {
                    "type": "string",
                    "description": "Text to find (must match exactly)",
                },
                "replace": {
                    "type": "string",
                    "description": "Text to replace with",
                },
            },
            ["path", "find", "replace"],
        )

    async def execute(
        self, execution: ToolExecution, path: str = "", find: str = "", replace: str = "", **kwargs: Any
    ) -> ToolResult:
        if not path or not find:
            return ToolResult("Error: path and find are required", "Missing fields")

        original = self.source.read(path)
        if original is None:
            return ToolResult(f"Note not found: {path}. Use list_notes to find correct path.", "Not found")

        if find not in original:
            return ToolResult(
                f"Text to replace not found in {path}. Read the note first to get exact text.", "Not found"
            )

        proposed = original.replace(find, replace, 1)
        diff = generate_diff(original, proposed, path)

        # Show diff preview in approval
        preview_lines = diff.split("\n")[:DIFF_PREVIEW_LINES]
        diff_preview = "\n".join(preview_lines)
        if len(diff.split("\n")) > DIFF_PREVIEW_LINES:
            diff_preview += "\n... (truncated)"

        await execution.require_approval(path, diff=diff_preview)

        # Apply the edit
        success = self.source.write(path, proposed)
        if success:
            lines_changed = len([l for l in diff.split("\n") if l.startswith("+") or l.startswith("-")]) - 2
            return ToolResult(
                content=f"Applied edit to: {path}",
                preview="Edited",
                metadata={"diff": diff, "lines_changed": max(0, lines_changed)},
            )
        return ToolResult(f"Error writing to {path}", "Write failed")


class CreateNoteTool(Tool):
    """Create a new note. Must be approved by user."""

    name = "create_note"
    description = CREATE_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource

    def __init__(self, source: NotesSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "path": {
                    "type": "string",
                    "description": "Relative path for the new note (e.g., 'projects/new-idea.md')",
                },
                "content": {
                    "type": "string",
                    "description": "Content for the new note",
                },
            },
            ["path", "content"],
        )

    async def execute(self, execution: ToolExecution, path: str = "", content: str = "", **kwargs: Any) -> ToolResult:
        if not path or not content:
            return ToolResult("Error: path and content are required", "Missing fields")

        if not path.endswith(".md"):
            path = path + ".md"

        if self.source.exists(path):
            return ToolResult(
                f"Note already exists: {path}. Use edit_note to modify or choose different path.", "Exists"
            )

        preview_content = content[:CONTENT_PREVIEW_LIMIT]
        if len(content) > CONTENT_PREVIEW_LIMIT:
            preview_content += "\n... (truncated)"

        await execution.require_approval(path, preview=preview_content)

        # Create the note
        success = self.source.write(path, content)
        if success:
            return ToolResult(f"Created note: {path}", "Created")
        return ToolResult(f"Error creating {path}", "Create failed")


class DeleteNoteTool(Tool):
    """Delete a note. Must be approved by user."""

    name = "delete_note"
    description = DELETE_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource

    def __init__(self, source: NotesSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "path": {
                    "type": "string",
                    "description": "Relative path to the note file",
                },
            },
            ["path"],
        )

    async def execute(self, execution: ToolExecution, path: str = "", **kwargs: Any) -> ToolResult:
        if not path:
            return ToolResult("Error: path is required", "Missing path")

        original = self.source.read(path)
        if original is None:
            return ToolResult(f"Note not found: {path}. Use list_notes to find correct path.", "Not found")

        await execution.require_approval(path)

        # Delete the note
        success = self.source.delete(path)
        if success:
            return ToolResult(f"Deleted: {path}", "Deleted")
        return ToolResult(f"Error deleting {path}", "Delete failed")


class MoveNoteTool(Tool):
    """Move or rename a note. Must be approved by user."""

    name = "move_note"
    description = MOVE_NOTE_DESCRIPTION
    mutates = True
    source_type = NotesSource

    def __init__(self, source: NotesSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "path": {
                    "type": "string",
                    "description": "Current relative path to the note",
                },
                "new_path": {
                    "type": "string",
                    "description": "New relative path for the note",
                },
            },
            ["path", "new_path"],
        )

    async def execute(self, execution: ToolExecution, path: str = "", new_path: str = "", **kwargs: Any) -> ToolResult:
        if not path or not new_path:
            return ToolResult("Error: path and new_path are required", "Missing fields")

        if not new_path.endswith(".md"):
            new_path = new_path + ".md"

        if not self.source.exists(path):
            return ToolResult(f"Note not found: {path}. Use list_notes to find correct path.", "Not found")

        if self.source.exists(new_path):
            return ToolResult(
                f"Destination already exists: {new_path}. Choose different path or delete existing first.", "Exists"
            )

        await execution.require_approval(f"{path} → {new_path}")

        # Move the note
        success = self.source.move(path, new_path)
        if success:
            return ToolResult(f"Moved: `{path}` → `{new_path}`", "Moved")
        return ToolResult(f"Error moving {path}", "Move failed")


class SearchNotesTool(Tool):
    name = "search_notes"
    description = SEARCH_NOTES_DESCRIPTION
    source_type = NotesSource

    def __init__(
        self,
        source: NotesSource,
        search_index: Any | None = None,
    ):
        self.source = source
        self.search_index = search_index

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Maximum results (default: 10)"},
            },
            ["query"],
        )

    async def execute(self, execution: ToolExecution, query: str = "", limit: int = 10, **kwargs: Any) -> ToolResult:
        if not query:
            return ToolResult("Error: query is required", "Missing query")

        query = simplify_query(query)

        # Hybrid search if available
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
                    return ToolResult("\n".join(output), f"{len(results)} notes")
            except Exception as e:
                logger.warning("Hybrid search failed, falling back to text search: %s", e)

        # Fallback to text search
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
            return ToolResult(f"No notes found for '{query}'", "0 notes")

        output = []
        for title, path, snippet in results:
            output.append(f"• {title}")
            output.append(f"  path: `{path}`")
            if snippet:
                output.append(f"  {snippet}")

        return ToolResult("\n".join(output), f"{len(results)} notes")
