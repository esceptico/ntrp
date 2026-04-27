from dataclasses import dataclass


@dataclass(frozen=True)
class ToolResult:
    content: str
    preview: str
    is_error: bool = False
    data: dict | None = None

    @staticmethod
    def error(message: str) -> "ToolResult":
        return ToolResult(content=message, preview="Error", is_error=True)


@dataclass(frozen=True)
class ToolMeta:
    name: str
    display_name: str
    mutates: bool
    volatile: bool
