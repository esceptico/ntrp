from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ntrp.tools.core.base import Tool, ToolResult
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


_WRITE_SCRATCHPAD_DESCRIPTION = """Your private workspace for internal reasoning that doesn't fit in context.

This is YOUR scratch space — never use it to "save something for the user."
If the user asks you to write/draft something, put it directly in your response.

USE FOR:
- Breaking down complex multi-step plans you need to track
- Intermediate results from research/exploration you'll reference later
- Temporary structured data (comparisons, aggregations) mid-task

NOT FOR:
- Drafts, summaries, or content intended for the user — just respond with it
- Anything the user asked you to "save" or "write down" — use memory or respond directly

PARAMETERS:
- content: What to save (markdown supported)
- key: Namespace for the note (default: "default")"""

_READ_SCRATCHPAD_DESCRIPTION = """Read previously saved working notes.

PARAMETERS:
- key: Namespace to read from (default: "default")

Returns empty if no note exists for the key."""

_LIST_SCRATCHPAD_DESCRIPTION = """List all saved scratchpad keys for this session.

Returns a list of existing keys, or empty if none exist."""


class WriteScratchpadInput(BaseModel):
    content: str = Field(description="Content to save")
    key: str = Field(default="default", description="Namespace for the note (default: 'default')")


class WriteScratchpadTool(Tool):
    name = "write_scratchpad"
    display_name = "WriteScratchpad"
    description = _WRITE_SCRATCHPAD_DESCRIPTION
    input_model = WriteScratchpadInput

    async def execute(
        self, execution: ToolExecution, content: str = "", key: str = "default", **kwargs: Any
    ) -> ToolResult:
        if not content:
            return ToolResult(content="Error: content is required", preview="Missing content", is_error=True)

        if len(content) > MAX_CONTENT_SIZE:
            return ToolResult(
                content=f"Error: content too large ({len(content)} chars, max {MAX_CONTENT_SIZE})",
                preview="Too large",
                is_error=True,
            )

        path = _scratchpad_path(execution.ctx.session_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")
        return ToolResult(content=f"Saved to scratchpad '{key}' ({len(content)} chars)", preview="Saved")


class ReadScratchpadInput(BaseModel):
    key: str = Field(default="default", description="Namespace to read (default: 'default')")


class ReadScratchpadTool(Tool):
    name = "read_scratchpad"
    display_name = "ReadScratchpad"
    description = _READ_SCRATCHPAD_DESCRIPTION
    input_model = ReadScratchpadInput

    async def execute(self, execution: ToolExecution, key: str = "default", **kwargs: Any) -> ToolResult:
        path = _scratchpad_path(execution.ctx.session_id, key)

        if not path.exists():
            return ToolResult(content=f"No scratchpad found for key '{key}'", preview="Empty")

        content = path.read_text(encoding="utf-8")
        return ToolResult(content=content, preview=f"Read {len(content)} chars")


class ListScratchpadTool(Tool):
    name = "list_scratchpad"
    display_name = "ListScratchpad"
    description = _LIST_SCRATCHPAD_DESCRIPTION
    input_model = None

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        scratch_dir = _scratchpad_dir(execution.ctx.session_id)

        if not scratch_dir.exists():
            return ToolResult(content="No scratchpad notes found", preview="Empty")

        keys = sorted(p.stem for p in scratch_dir.glob("*.md"))
        if not keys:
            return ToolResult(content="No scratchpad notes found", preview="Empty")

        listing = "\n".join(f"- {k}" for k in keys)
        return ToolResult(content=listing, preview=f"{len(keys)} keys")
