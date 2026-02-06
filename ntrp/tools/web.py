import json
from typing import Any

from ntrp.constants import EMBEDDING_TEXT_LIMIT, WEB_SEARCH_MAX_RESULTS
from ntrp.sources.base import WebSearchSource
from ntrp.tools.core.base import Tool, ToolResult, make_schema
from ntrp.tools.core.context import ToolExecution


class WebSearchTool(Tool):
    """Search the web using Exa's AI-powered search engine."""

    name = "web_search"
    description = "Search the web for information. Returns titles, URLs, and content snippets."
    source_type = WebSearchSource

    def __init__(self, source: WebSearchSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(self.name, self.description, {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "num_results": {
                "type": "integer",
                "description": f"Number of results (default: 5, max: {WEB_SEARCH_MAX_RESULTS})",
            },
            "category": {
                "type": "string",
                "description": "Filter by category: company, research paper, news, pdf, github, tweet",
                "enum": ["company", "research paper", "news", "pdf", "github", "tweet"],
            },
        }, ["query"])

    async def execute(
        self,
        execution: ToolExecution,
        query: str = "",
        num_results: int = 5,
        category: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        if not query.strip():
            return ToolResult("Error: query is required", "Missing query")

        try:
            results = self.source.search_with_details(
                query=query,
                num_results=min(max(num_results, 1), WEB_SEARCH_MAX_RESULTS),
                category=category,
            )

            formatted = []
            for r in results:
                item: dict[str, Any] = {
                    "title": r.title,
                    "url": r.url,
                }
                if r.published_date:
                    item["date"] = r.published_date
                if r.summary:
                    item["summary"] = r.summary
                if r.highlights:
                    item["highlights"] = r.highlights[:3]
                formatted.append(item)

            content = json.dumps({"query": query, "results": formatted}, indent=2, ensure_ascii=False)
            return ToolResult(content, f"{len(formatted)} results")

        except Exception as e:
            return ToolResult(f"Error: Search failed: {e}", "Search failed")


class WebFetchTool(Tool):
    """Fetch and extract content from a webpage."""

    name = "web_fetch"
    description = "Fetch content from a URL. Returns the page text in readable format."
    source_type = WebSearchSource

    def __init__(self, source: WebSearchSource):
        self.source = source

    @property
    def schema(self) -> dict:
        return make_schema(self.name, self.description, {
            "url": {
                "type": "string",
                "description": "The URL to fetch",
            },
        }, ["url"])

    async def execute(self, execution: ToolExecution, url: str = "", **kwargs: Any) -> ToolResult:
        if not url.strip():
            return ToolResult("Error: url is required", "Missing url")

        if not url.startswith(("http://", "https://")):
            return ToolResult(f"Invalid URL: must start with http:// or https://. Got: {url}", "Invalid url")

        try:
            results = self.source.get_contents([url])

            if results:
                r = results[0]
                text = r.text or ""
                lines = text.count("\n") + 1
                output = []
                if r.title:
                    output.append(f"Title: {r.title}")
                if r.published_date:
                    output.append(f"Date: {r.published_date}")
                if r.author:
                    output.append(f"Author: {r.author}")
                output.append("")
                if text:
                    if len(text) > EMBEDDING_TEXT_LIMIT:
                        text = text[:EMBEDDING_TEXT_LIMIT] + "\n\n... [truncated]"
                    output.append(text)
                return ToolResult("\n".join(output), f"Fetched {lines} lines")
            return ToolResult("No content fetched. Page may be empty or require JavaScript.", "Empty")
        except Exception as e:
            return ToolResult(f"Error fetching URL: {e}", "Fetch failed")
