import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import EMBEDDING_TEXT_LIMIT, WEB_SEARCH_MAX_RESULTS
from ntrp.sources.base import WebSearchSource
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

WEB_SEARCH_DESCRIPTION = "Search the web for information. Returns titles, URLs, and content snippets."

WEB_FETCH_DESCRIPTION = "Fetch content from a URL. Returns the page text in readable format."


class WebSearchCategory(StrEnum):
    company = "company"
    research_paper = "research paper"
    news = "news"
    pdf = "pdf"
    github = "github"
    tweet = "tweet"


_DEFAULT_SEARCH_RESULTS = 5


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query")
    num_results: int = Field(
        default=_DEFAULT_SEARCH_RESULTS,
        description=f"Number of results (default: {_DEFAULT_SEARCH_RESULTS}, max: {WEB_SEARCH_MAX_RESULTS})",
    )
    category: WebSearchCategory | None = Field(
        default=None,
        description="Filter by category: company, research paper, news, pdf, github, tweet",
    )


class WebSearchTool(Tool):
    name = "web_search"
    display_name = "WebSearch"
    description = WEB_SEARCH_DESCRIPTION
    source_type = WebSearchSource
    input_model = WebSearchInput

    async def execute(
        self,
        execution: ToolExecution,
        query: str,
        num_results: int = _DEFAULT_SEARCH_RESULTS,
        category: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        source = execution.ctx.get_source(WebSearchSource)
        try:
            results = source.search_with_details(
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
            return ToolResult(content=content, preview=f"{len(formatted)} results")

        except Exception as e:
            return ToolResult(content=f"Error: Search failed: {e}", preview="Search failed", is_error=True)


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch")


class WebFetchTool(Tool):
    name = "web_fetch"
    display_name = "WebFetch"
    description = WEB_FETCH_DESCRIPTION
    source_type = WebSearchSource
    input_model = WebFetchInput

    async def execute(self, execution: ToolExecution, url: str, **kwargs: Any) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                content=f"Invalid URL: must start with http:// or https://. Got: {url}",
                preview="Invalid url",
                is_error=True,
            )

        source = execution.ctx.get_source(WebSearchSource)
        try:
            results = source.get_contents([url])

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
                return ToolResult(content="\n".join(output), preview=f"Fetched {lines} lines")
            return ToolResult(content="No content fetched. Page may be empty or require JavaScript.", preview="Empty")
        except Exception as e:
            return ToolResult(content=f"Error fetching URL: {e}", preview="Fetch failed", is_error=True)
