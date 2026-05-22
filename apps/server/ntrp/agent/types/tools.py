from dataclasses import dataclass

from ntrp.core.content import ContentBlock


@dataclass(frozen=True)
class ToolResult:
    content: str
    preview: str
    is_error: bool = False
    data: dict | None = None
    model_content: tuple[ContentBlock, ...] = ()

    @staticmethod
    def error(message: str) -> "ToolResult":
        return ToolResult(content=message, preview="Error", is_error=True)


@dataclass(frozen=True)
class ToolMeta:
    name: str
    display_name: str
    kind: str = "tool"
