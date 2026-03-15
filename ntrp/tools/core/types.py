from dataclasses import dataclass


@dataclass(frozen=True)
class ToolResult:
    content: str
    preview: str
    is_error: bool = False
    data: dict | None = None


@dataclass(frozen=True)
class ApprovalInfo:
    description: str
    preview: str | None
    diff: str | None
