# Back-compat: module renamed to ntrp.tools.web in 0.3.2.
# Keeps `from ntrp.tools.web_fetch import WebFetchTool` working for custom tools in ~/.ntrp/tools/.
from ntrp.tools.web import WebFetchTool, WebSearchTool

__all__ = ["WebFetchTool", "WebSearchTool"]
