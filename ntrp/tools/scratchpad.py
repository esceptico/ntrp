from pathlib import Path
from typing import Any

from ntrp.tools.core.base import Tool, ToolResult, make_schema
from ntrp.tools.core.context import ToolExecution

SCRATCHPAD_BASE = Path("/tmp/ntrp")
MAX_CONTENT_SIZE = 50_000


def _scratchpad_dir(session_id: str) -> Path:
    return SCRATCHPAD_BASE / session_id / "scratch"


def _scratchpad_path(session_id: str, key: str) -> Path:
    base = _scratchpad_dir(session_id)
    path = (base / f"{key}.md").resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError(f"Invalid scratchpad key: {key}")
    return path


_WRITE_SCRATCHPAD_DESCRIPTION = """Save working notes for this session.

USE FOR:
- Plans and task tracking during complex operations
- Intermediate results from multi-step exploration
- Temporary data that needs to persist across tool calls

PARAMETERS:
- content: What to save (markdown supported)
- key: Namespace for the note (default: "default")

Multiple keys let you organize different types of notes."""

_READ_SCRATCHPAD_DESCRIPTION = """Read previously saved working notes.

PARAMETERS:
- key: Namespace to read from (default: "default")

Returns empty if no note exists for the key."""

_LIST_SCRATCHPAD_DESCRIPTION = """List all saved scratchpad keys for this session.

Returns a list of existing keys, or empty if none exist."""


class WriteScratchpadTool(Tool):
    name = "write_scratchpad"
    description = _WRITE_SCRATCHPAD_DESCRIPTION

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "content": {
                    "type": "string",
                    "description": "Content to save",
                },
                "key": {
                    "type": "string",
                    "description": "Namespace for the note (default: 'default')",
                },
            },
            ["content"],
        )

    async def execute(
        self, execution: ToolExecution, content: str = "", key: str = "default", **kwargs: Any
    ) -> ToolResult:
        if not content:
            return ToolResult("Error: content is required", "Missing content")

        if len(content) > MAX_CONTENT_SIZE:
            return ToolResult(
                f"Error: content too large ({len(content)} chars, max {MAX_CONTENT_SIZE})",
                "Too large",
            )

        path = _scratchpad_path(execution.ctx.session_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")
        return ToolResult(f"Saved to scratchpad '{key}' ({len(content)} chars)", "Saved")


class ReadScratchpadTool(Tool):
    name = "read_scratchpad"
    description = _READ_SCRATCHPAD_DESCRIPTION

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "key": {
                    "type": "string",
                    "description": "Namespace to read (default: 'default')",
                },
            },
        )

    async def execute(self, execution: ToolExecution, key: str = "default", **kwargs: Any) -> ToolResult:
        path = _scratchpad_path(execution.ctx.session_id, key)

        if not path.exists():
            return ToolResult(f"No scratchpad found for key '{key}'", "Empty")

        content = path.read_text(encoding="utf-8")
        return ToolResult(content, f"Read {len(content)} chars")


class ListScratchpadTool(Tool):
    name = "list_scratchpad"
    description = _LIST_SCRATCHPAD_DESCRIPTION

    @property
    def schema(self) -> dict:
        return make_schema(self.name, self.description, {})

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        scratch_dir = _scratchpad_dir(execution.ctx.session_id)

        if not scratch_dir.exists():
            return ToolResult("No scratchpad notes found", "Empty")

        keys = sorted(p.stem for p in scratch_dir.glob("*.md"))
        if not keys:
            return ToolResult("No scratchpad notes found", "Empty")

        listing = "\n".join(f"- {k}" for k in keys)
        return ToolResult(listing, f"{len(keys)} keys")
