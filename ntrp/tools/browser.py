from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import BROWSER_TITLE_TRUNCATE, URL_TRUNCATE
from ntrp.sources.base import BrowserSource
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.utils import truncate

BROWSER_DESCRIPTION = """Browse or search browser history.

Without query: lists recent browser history sorted by visit time. Use days to control time range.
With query: searches by page content or URL. Use specific keywords like site names or topics.

Returns page titles and URLs."""


class BrowserInput(BaseModel):
    query: str | None = Field(default=None, description="Search query. Omit to list recent history.")
    days: int = Field(default=7, description="How many days back to look when listing (default: 7)")
    limit: int = Field(default=30, description="Maximum results (default: 30)")


class BrowserTool(Tool):
    name = "browser"
    display_name = "Browser"
    description = BROWSER_DESCRIPTION
    source_type = BrowserSource
    input_model = BrowserInput

    def __init__(self, source: BrowserSource):
        self.source = source

    async def execute(
        self, execution: ToolExecution, query: str | None = None, days: int = 7, limit: int = 30, **kwargs: Any
    ) -> ToolResult:
        if query:
            return self._search(query, limit)
        return self._list(days, limit)

    def _list(self, days: int, limit: int) -> ToolResult:
        items = self.source.list_recent(days=days, limit=limit)

        if not items:
            return ToolResult(content=f"No browser history in last {days} days", preview="0 items")

        output = []
        for item in items[:limit]:
            title = truncate(item.title or item.identity, BROWSER_TITLE_TRUNCATE)
            date_str = item.timestamp.strftime("%Y-%m-%d") if item.timestamp else ""
            output.append(f"• {title}" + (f" ({date_str})" if date_str else ""))

        return ToolResult(content="\n".join(output), preview=f"{len(items)} items")

    def _search(self, query: str, limit: int) -> ToolResult:
        urls = self.source.search(query)
        if not urls:
            return ToolResult(content=f"No browser history found for '{query}'", preview="0 results")

        output = []
        for url in list(urls)[:limit]:
            info = self.source.read(url)
            if info:
                lines = info.split("\n")
                title = next(
                    (line.replace("Title: ", "") for line in lines if line.startswith("Title:")),
                    truncate(url, URL_TRUNCATE),
                )
                output.append(f"• {truncate(title, URL_TRUNCATE)}")
                output.append(f"  {truncate(url, URL_TRUNCATE)}")
            else:
                output.append(f"• {truncate(url, URL_TRUNCATE)}")

        return ToolResult(content="\n".join(output), preview=f"{min(len(urls), limit)} results")
