import difflib
import json
from typing import Any

from pydantic import BaseModel, Field

from ntrp.config import NTRP_DIR
from ntrp.tools.core.base import ApprovalInfo, Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

DIRECTIVES_PATH = NTRP_DIR / "directives.json"

DESCRIPTION = """Set custom directives that shape your behavior.

These directives persist across conversations and are injected into your system prompt.
Use this when the user asks you to change how you behave — style, tone, things to do or avoid.

Pass the FULL desired directives — this replaces any previous content.
Read current directives first (if any), then write the updated version."""


class SetDirectivesInput(BaseModel):
    directives: str = Field(description="The full custom directives text.")


class SetDirectivesTool(Tool):
    name = "set_directives"
    display_name = "Set Directives"
    description = DESCRIPTION
    mutates = True
    input_model = SetDirectivesInput

    async def approval_info(self, directives: str, **kwargs: Any) -> ApprovalInfo:
        current = load_directives() or ""
        diff = _diff(current, directives)
        return ApprovalInfo(description="Update directives", preview=None, diff=diff)

    async def execute(
        self,
        execution: ToolExecution,
        directives: str,
        **kwargs: Any,
    ) -> ToolResult:
        save_directives(directives)
        if not directives.strip():
            return ToolResult(content="Directives cleared.", preview="Cleared")
        return ToolResult(
            content=f"Directives updated:\n{directives}",
            preview="Directives set",
        )


def _diff(old: str, new: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="directives", tofile="directives", lineterm="")
    return "\n".join(diff)


def load_directives() -> str | None:
    if not DIRECTIVES_PATH.exists():
        return None
    try:
        data = json.loads(DIRECTIVES_PATH.read_text())
        text = data.get("content", "").strip()
        return text or None
    except (json.JSONDecodeError, OSError):
        return None


def save_directives(content: str) -> None:
    content = content.strip()
    if not content:
        if DIRECTIVES_PATH.exists():
            DIRECTIVES_PATH.unlink()
        return
    DIRECTIVES_PATH.write_text(json.dumps({"content": content}))
