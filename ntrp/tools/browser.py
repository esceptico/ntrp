from typing import Any

from ntrp.constants import BROWSER_TITLE_TRUNCATE, URL_TRUNCATE
from ntrp.sources.base import BrowserSource
from ntrp.tools.core.base import Tool, ToolResult, make_schema
from ntrp.tools.core.context import ToolExecution
from ntrp.utils import truncate

LIST_BROWSER_DESCRIPTION = "List recent browser history."

SEARCH_BROWSER_DESCRIPTION = "Search browser history by content or URL."


class ListBrowserTool(Tool):
    name = "list_browser"
    description = LIST_BROWSER_DESCRIPTION
    source_type = BrowserSource

    def __init__(self, source: BrowserSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(
            self.name,
            self.description,
            {
                "days": {"type": "integer", "description": "How many days back to look (default: 7)"},
                "limit": {"type": "integer", "description": "Maximum results (default: 30)"},
            },
        )

    async def execute(self, execution: ToolExecution, days: int = 7, limit: int = 30, **kwargs: Any) -> ToolResult:
        items = self.source.list_recent(days=days, limit=limit)

        if not items:
            return ToolResult(f"No browser history in last {days} days", "0 items")

        output = []
        for item in items[:limit]:
            title = truncate(item.title or item.identity, BROWSER_TITLE_TRUNCATE)
            date_str = item.timestamp.strftime("%Y-%m-%d") if item.timestamp else ""
            output.append(f"• {title}" + (f" ({date_str})" if date_str else ""))

        return ToolResult("\n".join(output), f"{len(items)} items")


class SearchBrowserTool(Tool):
    name = "search_browser"
    description = SEARCH_BROWSER_DESCRIPTION
    source_type = BrowserSource

    def __init__(self, source: BrowserSource):
        self.source = source

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

        urls = self.source.search(query)
        if not urls:
            return ToolResult(f"No browser history found for '{query}'", "0 results")

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

        return ToolResult("\n".join(output), f"{min(len(urls), limit)} results")
