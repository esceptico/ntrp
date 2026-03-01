# Back-compat: module renamed to ntrp.tools.web in 0.3.2.
# Keeps `from ntrp.tools.web_fetch import WebFetchTool` working for custom tools in ~/.ntrp/tools/.
import warnings

from ntrp.tools.web import WebFetchTool, WebSearchTool

warnings.warn(
    "ntrp.tools.web_fetch is deprecated, use ntrp.tools.web instead. This module will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["WebFetchTool", "WebSearchTool"]
