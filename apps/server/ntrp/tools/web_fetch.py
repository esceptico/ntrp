import warnings

from ntrp.integrations.web.tools import web_fetch_tool, web_search_tool

warnings.warn(
    "ntrp.tools.web_fetch is deprecated, use ntrp.integrations.web.tools instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["web_fetch_tool", "web_search_tool"]
