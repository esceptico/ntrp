# Integrations

An **Integration** bundles everything ntrp needs to connect to an external service: client code, agent tools, notifier classes, and config fields. Each integration lives in its own directory under `ntrp/integrations/` and is registered once in `ALL_INTEGRATIONS`.

## Anatomy

```
ntrp/integrations/slack/
  __init__.py    # exports the SLACK Integration declaration
  client.py      # SlackClient — the HTTP/API wrapper
  tools.py       # SlackSearchTool, SlackChannelTool, ... (classes)
  notifier.py    # SlackNotifier (optional)
```

An integration is a frozen dataclass:

```python
@dataclass(frozen=True)
class Integration:
    id: str                                             # "slack"
    label: str                                          # "Slack"
    service_fields: list[IntegrationField]              # user-facing config keys
    tools: list[type[Tool]]                             # agent tools contributed
    notifier_class: type[Notifier] | None               # optional notifier
    build: Callable[[Config], object | None] | None     # returns client, or None if unconfigured
```

`build` receives the current `Config` and returns a client instance, or `None` if the integration isn't configured. If it raises, the error is captured and surfaced to the UI.

## Adding a new integration

1. Create `ntrp/integrations/<name>/` with:
   - `client.py` — API wrapper, no inheritance from any protocol
   - `tools.py` — `Tool` subclasses that look up the client via `execution.ctx.get_client("<name>", YourClient)`
   - `notifier.py` — optional `Notifier` subclass
   - `__init__.py` — exports a module-level `<NAME>: Integration` constant
2. Add `<NAME>` to `ALL_INTEGRATIONS` in `ntrp/integrations/__init__.py`
3. Add any new config fields to `ntrp/config.py` (e.g. `linear_api_key: str | None = Field(default=None, alias="LINEAR_API_KEY")`)

That's it. The registry handles tool registration, notifier class lookup, service endpoint listing, sidebar rendering, and hot reload.

## Example: minimal integration

```python
# ntrp/integrations/linear/__init__.py
from ntrp.config import Config
from ntrp.integrations.base import Integration, IntegrationField
from ntrp.integrations.linear.client import LinearClient
from ntrp.integrations.linear.tools import LinearIssuesTool, LinearSearchTool


def _build(config: Config) -> LinearClient | None:
    if not config.linear_api_key:
        return None
    return LinearClient(api_key=config.linear_api_key)


LINEAR = Integration(
    id="linear",
    label="Linear",
    service_fields=[
        IntegrationField("linear_api_key", "Linear API key", secret=True, env_var="LINEAR_API_KEY"),
    ],
    tools=[LinearIssuesTool, LinearSearchTool],
    build=_build,
)
```

```python
# ntrp/integrations/linear/tools.py
from typing import Any

from pydantic import BaseModel, Field

from ntrp.integrations.linear.client import LinearClient
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class LinearSearchInput(BaseModel):
    query: str = Field(description="Search query")


class LinearSearchTool(Tool):
    name = "linear_search"
    display_name = "LinearSearch"
    description = "Search Linear issues by text"
    requires = frozenset({"linear"})
    input_model = LinearSearchInput

    async def execute(self, execution: ToolExecution, query: str, **kwargs: Any) -> ToolResult:
        client = execution.ctx.get_client("linear", LinearClient)
        issues = await client.search(query)
        return ToolResult(content=format_issues(issues), preview=f"{len(issues)} issues")
```

## Native integration vs MCP

**Use a native integration** when you need:
- Deep indexing into memory (vector search across content)
- Platform-specific auth (Google OAuth, Slack dual-token, PKCE)
- Notifier integration (proactive sends)
- Custom query semantics beyond what an MCP tool exposes
- In-process performance

**Use MCP** when:
- A vendor ships an official MCP server
- You want tools without writing API client code
- It's a quick experiment — you can promote to native later

MCP servers appear alongside native integrations in `GET /tool-providers` with `kind="mcp"`.

## Indexable integrations

Integrations whose clients implement `async def scan() -> list[RawItem]` are automatically picked up by the indexer. `Obsidian`, `Gmail`, and `Calendar` are indexable today. Nothing else changes — the runtime detects `isinstance(client, Indexable)` during `_sync_indexables`.

## Hot reload

`runtime.reload_config()` rebuilds all integration clients from the fresh config. It's called automatically when a user connects/disconnects a service via the UI, and is exposed manually at `POST /settings/reload` for after direct `.env` / `settings.json` edits.

## Notifier-only integrations

An integration with `build=None` contributes only a notifier class (e.g. Telegram). It doesn't appear in the sources sidebar but does show in the notifier type picker.

## Shared auth (Google)

Gmail and Calendar share the same Google OAuth flow. The helper module `ntrp/integrations/google_auth/` isn't an Integration — it's a shared module both `gmail/` and `calendar/` import from. If two integrations share auth, follow the same pattern: one helper module, two separate Integration definitions.
