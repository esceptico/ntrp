import os
from pathlib import Path
from typing import Any

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

SCRATCHPAD_BASE = Path("/tmp/ntrp")


def _scratchpad_path(session_id: str, key: str) -> Path:
    return SCRATCHPAD_BASE / session_id / "scratch" / f"{key}.md"


class WriteScratchpadTool(Tool):
    name = "write_scratchpad"
    description = """Save working notes for this session.

USE FOR:
- Plans and task tracking during complex operations
- Intermediate results from multi-step exploration
- Temporary data that needs to persist across tool calls

PARAMETERS:
- content: What to save (markdown supported)
- key: Namespace for the note (default: "default")

Multiple keys let you organize different types of notes."""

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Content to save",
                    },
                    "key": {
                        "type": "string",
                        "description": "Namespace for the note (default: 'default')",
                    },
                },
                "required": ["content"],
            },
        }

    async def execute(
        self, execution: ToolExecution, content: str = "", key: str = "default", **kwargs: Any
    ) -> ToolResult:
        if not content:
            return ToolResult("Error: content is required", "Missing content")

        path = _scratchpad_path(execution.ctx.session_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")
        return ToolResult(f"Saved to scratchpad '{key}' ({len(content)} chars)", "Saved")


class ReadScratchpadTool(Tool):
    name = "read_scratchpad"
    description = """Read previously saved working notes.

PARAMETERS:
- key: Namespace to read from (default: "default")

Returns empty if no note exists for the key."""

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Namespace to read (default: 'default')",
                    },
                },
            },
        }

    async def execute(self, execution: ToolExecution, key: str = "default", **kwargs: Any) -> ToolResult:
        path = _scratchpad_path(execution.ctx.session_id, key)

        if not path.exists():
            return ToolResult(f"No scratchpad found for key '{key}'", "Empty")

        content = path.read_text(encoding="utf-8")
        return ToolResult(content, f"Read {len(content)} chars")
