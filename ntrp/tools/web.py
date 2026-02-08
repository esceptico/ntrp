import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import EMBEDDING_TEXT_LIMIT, WEB_SEARCH_MAX_RESULTS
from ntrp.sources.base import WebSearchSource
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

WEB_SEARCH_DESCRIPTION = "Search the web for information. Returns titles, URLs, and content snippets."

WEB_FETCH_DESCRIPTION = "Fetch content from a URL. Returns the page text in readable format."


class WebSearchCategory(str, Enum):
    company = "company"
    research_paper = "research paper"
    news = "news"
    pdf = "pdf"
    github = "github"
    tweet = "tweet"


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query")
    num_results: int = Field(default=5, description=f"Number of results (default: 5, max: {WEB_SEARCH_MAX_RESULTS})")
    category: WebSearchCategory | None = Field(
        default=None,
        description="Filter by category: company, research paper, news, pdf, github, tweet",
    )


class WebSearchTool(Tool):
    name = "web_search"
    description = WEB_SEARCH_DESCRIPTION
    source_type = WebSearchSource
    input_model = WebSearchInput

    def __init__(self, source: WebSearchSource):
        self.source = source

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


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch")


class WebFetchTool(Tool):
    name = "web_fetch"
    description = WEB_FETCH_DESCRIPTION
    source_type = WebSearchSource
    input_model = WebFetchInput

    def __init__(self, source: WebSearchSource):
        self.source = source

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
