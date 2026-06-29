from dataclasses import dataclass

from ntrp.core.content import ContentBlock


@dataclass(frozen=True)
class ToolResult:
    content: str
    preview: str
    is_error: bool = False
    data: dict | None = None
    model_content: tuple[ContentBlock, ...] = ()
    # Set by tools that fetch an external resource (file, web page, etc.).
    # Shape: {"kind": str, "ref": str, "title": str | None}. Collected onto
    # the run and folded into the episode's source_refs by the chat connector.
    source_ref: dict | None = None

    @staticmethod
    def error(message: str) -> "ToolResult":
        return ToolResult(content=message, preview="Error", is_error=True)


@dataclass(frozen=True)
class ToolMeta:
    name: str
    display_name: str
    kind: str = "tool"
    # Additive UI rendering hints — semantic, library-agnostic. The desktop app
    # maps `icon` to a glyph and pluralizes grouped runs with `noun`; `source`
    # is the integration category. All optional; absent for uncategorized tools.
    icon: str | None = None
    noun: str | None = None
    source: str | None = None
