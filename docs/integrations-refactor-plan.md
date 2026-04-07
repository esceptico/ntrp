# Integrations Refactor — Implementation Plan

## Goal

Replace the scattered `sources/` + `tools/specs.py` + `notifiers/service.py` + `SERVICE_KEY_FIELDS` + `SERVICE_META` model with a single `Integration` concept where each integration lives in its own directory and is registered once in a central list.

**Definition of done:** adding a new integration requires one new directory under `ntrp/integrations/` and one line in `ntrp/integrations/__init__.py`. No edits to config.py, routers, notifier service, UI sidebar, or tool specs.

## Non-goals

- **No MCP changes.** MCP stays in `ntrp/mcp/`, gets a thin `list_providers()` method for uniform UI reporting. Internals untouched.
- **No memory changes.** Memory is special (own storage, consolidation loop). Stays outside integrations.
- **No config file format change.** Keep flat settings (`slack_bot_token` at top level). Can revisit later.
- **No tool API change.** Tools still extend `Tool`, take `ToolExecution`, return `ToolResult`. Only how they find their client changes.

---

## Target shape

```
ntrp/integrations/
  __init__.py              # ALL_INTEGRATIONS list — the only registration point
  base.py                  # Integration, IntegrationField, IntegrationHealth, ToolProviderStatus
  registry.py              # IntegrationRegistry: build all, query, health, tool merging
  slack/
    __init__.py            # exports SLACK: Integration
    client.py              # SlackClient (was sources/slack.py SlackSource)
    tools.py               # SlackSearchTool, SlackChannelTool, etc. (was tools/slack.py)
    notifier.py            # SlackNotifier (was notifiers/slack.py)
  gmail/
    __init__.py
    client.py              # Gmail wrapper (was sources/google/gmail.py)
    tools.py               # EmailsTool, ReadEmailTool, SendEmailTool
    notifier.py            # EmailNotifier (was notifiers/email.py)
  calendar/
    __init__.py
    client.py              # Calendar wrapper
    tools.py               # CalendarTool, CreateCalendarEventTool, etc.
  obsidian/
    __init__.py
    client.py              # ObsidianSource
    tools.py               # NotesTool, ReadNoteTool, EditNoteTool, etc.
  web/
    __init__.py
    client.py              # ExaWebSource | DDGSWebSource resolution
    tools.py               # WebSearchTool, WebFetchTool
  telegram/
    __init__.py            # notifier-only integration
    notifier.py            # TelegramNotifier
  google_auth/
    __init__.py
    auth.py                # shared Google OAuth for gmail + calendar
    (not a full Integration; imported by gmail/ and calendar/)
```

## Base types

```python
# ntrp/integrations/base.py
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from ntrp.config import Config
    from ntrp.notifiers.base import Notifier
    from ntrp.tools.core.base import Tool


@dataclass(frozen=True)
class IntegrationField:
    key: str                           # matches Config attribute name, e.g. "slack_bot_token"
    label: str                         # UI label
    secret: bool = False
    env_var: str | None = None         # for /settings/services display


@dataclass(frozen=True)
class IntegrationHealth:
    status: Literal["connected", "error", "not_configured"]
    detail: str | None = None


@dataclass(frozen=True)
class Integration:
    id: str                                             # "slack", "gmail", "telegram"
    label: str                                          # "Slack", "Gmail", "Telegram"
    service_fields: list[IntegrationField]              # keys users connect via Settings → Services
    tools: list[type["Tool"]] = ()                      # tool classes
    notifier_class: type["Notifier"] | None = None      # optional notifier
    build: Callable[["Config"], object | None] = None   # returns client, or None if unconfigured


@dataclass(frozen=True)
class ToolProviderStatus:
    id: str                            # "slack" or "mcp:server-name"
    label: str
    kind: Literal["native", "mcp"]
    health: IntegrationHealth
    tool_count: int
```

## Registry

```python
# ntrp/integrations/registry.py
from ntrp.config import Config
from ntrp.integrations.base import Integration, IntegrationHealth, ToolProviderStatus


class IntegrationRegistry:
    def __init__(self, integrations: list[Integration]):
        self._integrations = {i.id: i for i in integrations}
        self._clients: dict[str, object] = {}
        self._errors: dict[str, str] = {}

    def sync(self, config: Config) -> None:
        """Build/rebuild all integration clients from current config."""
        for id, integration in self._integrations.items():
            if integration.build is None:
                continue
            try:
                client = integration.build(config)
            except Exception as e:
                self._clients.pop(id, None)
                self._errors[id] = str(e)
                continue
            self._errors.pop(id, None)
            if client is None:
                self._clients.pop(id, None)
            else:
                self._clients[id] = client

    @property
    def clients(self) -> dict[str, object]:
        return dict(self._clients)

    def get_client(self, id: str) -> object | None:
        return self._clients.get(id)

    def get_integration(self, id: str) -> Integration | None:
        return self._integrations.get(id)

    def all_tools(self) -> list:
        """Flatten tools from all integrations (regardless of built state)."""
        out = []
        for integration in self._integrations.values():
            out.extend(integration.tools)
        return out

    def active_tools(self) -> list:
        """Only tools from integrations whose client successfully built."""
        out = []
        for id, integration in self._integrations.items():
            if id in self._clients or integration.build is None:
                out.extend(integration.tools)
        return out

    def notifier_classes(self) -> dict[str, type]:
        return {
            i.id: i.notifier_class
            for i in self._integrations.values()
            if i.notifier_class is not None
        }

    def service_fields(self) -> dict[str, list]:
        """For /settings/services endpoint."""
        return {i.id: i.service_fields for i in self._integrations.values() if i.service_fields}

    def list_providers(self) -> list[ToolProviderStatus]:
        out = []
        for id, integration in self._integrations.items():
            if integration.build is None:
                continue
            if id in self._clients:
                health = IntegrationHealth(status="connected")
            elif id in self._errors:
                health = IntegrationHealth(status="error", detail=self._errors[id])
            else:
                health = IntegrationHealth(status="not_configured")
            out.append(
                ToolProviderStatus(
                    id=id,
                    label=integration.label,
                    kind="native",
                    health=health,
                    tool_count=len(integration.tools),
                )
            )
        return out
```

## Tool client lookup

Tools currently do:
```python
source = execution.ctx.get_source(SlackSource, "slack")
```

New pattern:
```python
client = execution.ctx.get_client("slack", SlackClient)
```

Where `get_client` is a new method on `ToolContext` that reads from `ctx.services` (same dict, just type-narrowed via a generic). Keep `get_source` as a deprecated alias during migration so we can move one integration at a time.

---

## Phase breakdown

### Phase 0 — Prep (30 min)

- [ ] Create `ntrp/integrations/base.py` with `Integration`, `IntegrationField`, `IntegrationHealth`, `ToolProviderStatus`
- [ ] Create `ntrp/integrations/registry.py` with `IntegrationRegistry`
- [ ] Create `ntrp/integrations/__init__.py` with empty `ALL_INTEGRATIONS: list[Integration] = []`
- [ ] Add `get_client[T](id: str, type: type[T]) -> T | None` to `ToolContext` (reads from `self.services`)
- [ ] Verify tests still pass
- [ ] Commit: "feat(integrations): scaffold Integration base types and registry"

### Phase 1 — Pilot: migrate Slack (1 day)

Slack is the pilot because it's freshest and touches all three concerns (client, tools, notifier, indexable=no).

- [ ] Create `ntrp/integrations/slack/` directory
- [ ] Move `ntrp/sources/slack.py` → `ntrp/integrations/slack/client.py`
  - Rename `SlackSource` → `SlackClient` (drop the "Source" terminology)
  - Remove Protocol inheritance — it's just a client now
- [ ] Move `ntrp/tools/slack.py` → `ntrp/integrations/slack/tools.py`
  - Change `get_source(SlackSource, "slack")` → `get_client("slack", SlackClient)`
  - Import `SlackClient` from sibling module
- [ ] Move `ntrp/notifiers/slack.py` → `ntrp/integrations/slack/notifier.py`
- [ ] Create `ntrp/integrations/slack/__init__.py`:
  ```python
  from ntrp.integrations.base import Integration, IntegrationField
  from ntrp.integrations.slack.client import SlackClient
  from ntrp.integrations.slack.notifier import SlackNotifier
  from ntrp.integrations.slack.tools import (
      SlackChannelTool, SlackChannelsTool, SlackSearchTool,
      SlackThreadTool, SlackUserTool, SlackUsersTool,
  )

  def _build(config) -> SlackClient | None:
      if not config.slack_bot_token and not config.slack_user_token:
          return None
      return SlackClient(bot_token=config.slack_bot_token, user_token=config.slack_user_token)

  SLACK = Integration(
      id="slack",
      label="Slack",
      service_fields=[
          IntegrationField("slack_bot_token", "Slack (bot, xoxb-)", secret=True, env_var="SLACK_BOT_TOKEN"),
          IntegrationField("slack_user_token", "Slack (user, xoxp-)", secret=True, env_var="SLACK_USER_TOKEN"),
      ],
      tools=[SlackSearchTool, SlackChannelTool, SlackThreadTool, SlackChannelsTool, SlackUsersTool, SlackUserTool],
      notifier_class=SlackNotifier,
      build=_build,
  )
  ```
- [ ] Add `SLACK` to `ALL_INTEGRATIONS` in `ntrp/integrations/__init__.py`
- [ ] Delete old `SlackSource` Protocol from `ntrp/sources/base.py`
- [ ] Delete entries from `ntrp/sources/registry.py` for slack
- [ ] Delete slack from `_NOTIFIER_CLASSES` and `NOTIFIER_FIELDS` in `ntrp/notifiers/service.py` — registry provides it
- [ ] Delete slack tools from `ntrp/tools/specs.py` — registry provides them
- [ ] Delete `slack_bot_token`/`slack_user_token` from `SERVICE_KEY_FIELDS` and `SERVICE_META` — registry provides them
- [ ] Smoke test: start server, confirm slack tools still work, notifier still sends
- [ ] Commit: "feat(integrations): migrate Slack to Integration pattern"

### Phase 2 — Wire registry into runtime (half day)

This is the critical integration step. The registry must feed tools, notifiers, config endpoints, and sidebar.

- [ ] In `Runtime.__init__`: create `IntegrationRegistry(ALL_INTEGRATIONS)`
- [ ] In `Runtime.connect()`: call `self.integrations.sync(self.config)` after config is loaded
- [ ] In `Runtime.reload_config()`: call `self.integrations.sync(self.config)` after config refresh
- [ ] `Runtime.tool_services` property: merge `self.integrations.clients` into the services dict
- [ ] `Runtime._create_executor`: include tools from `self.integrations.active_tools()` alongside static ones
- [ ] `NotifierService.__init__` or `rebuild`: fetch classes from `integrations.notifier_classes()` instead of hardcoded dict
- [ ] `/settings/services` endpoint: dynamically include service fields from `integrations.service_fields()`
- [ ] `/settings/config` endpoint sources payload: build from `integrations.list_providers()` for native, keep existing MCP/memory/web/notes paths
- [ ] UI sidebar `SourcesSection.tsx`: fetch from `/integrations/providers` (new endpoint) or reuse `/settings/config` sources
- [ ] Smoke test: full chat flow with slack tool
- [ ] Commit: "feat(integrations): wire registry into runtime, executor, notifiers"

### Phase 3 — Migrate remaining native integrations (3-4 days)

One integration per day. Each follows the same pattern as Phase 1.

#### 3a. Web (simplest — no auth, no notifier, thin client) — 0.5 day

- [ ] Create `ntrp/integrations/web/`
- [ ] Move `ntrp/sources/exa.py` + `ntrp/sources/ddgs.py` → `ntrp/integrations/web/client.py` (or keep as submodules)
- [ ] Move `ntrp/tools/web.py` → `ntrp/integrations/web/tools.py`
- [ ] Create `WEB` integration in `__init__.py`:
  - `build`: resolve exa/ddgs based on `config.web_search` mode and `config.exa_api_key`
  - `service_fields`: `[IntegrationField("exa_api_key", ...)]`
- [ ] Delete from `sources/registry.py`, `tools/specs.py`, `SERVICE_KEY_FIELDS`
- [ ] Update `get_source(WebSearchSource, ...)` callers to `get_client("web", ...)`
- [ ] Delete `WebSearchSource` Protocol from `sources/base.py`
- [ ] Smoke test
- [ ] Commit

#### 3b. Obsidian (no notifier, indexable) — 0.5 day

- [ ] Create `ntrp/integrations/obsidian/`
- [ ] Move `ntrp/sources/obsidian.py` → `client.py`
- [ ] Move `ntrp/tools/notes.py` → `tools.py`
- [ ] `OBSIDIAN` integration
- [ ] **Indexable concern:** Obsidian implements `Indexable` protocol for auto-indexing. Keep `Indexable` as a separate protocol — the runtime's `_sync_indexables` already checks `isinstance(source, Indexable)`. Works identically with the new client.
- [ ] Delete `NotesSource` Protocol usage in tools
- [ ] Update tool calls
- [ ] Smoke test
- [ ] Commit

#### 3c. Gmail + Calendar (shared Google auth) — 1 day

The tricky one. They share `config.google` flag and `discover_gmail_tokens()` / `discover_calendar_tokens()`.

- [ ] Create `ntrp/integrations/google_auth/` (NOT a full integration — just a shared helper module)
- [ ] Move `ntrp/sources/google/auth.py` → `ntrp/integrations/google_auth/auth.py`
- [ ] Create `ntrp/integrations/gmail/`
  - `client.py` from `sources/google/gmail.py` (import auth from `google_auth`)
  - `tools.py` from `tools/email.py`
  - `notifier.py` from `notifiers/email.py`
  - `__init__.py` with `GMAIL` integration
  - `build`: check `config.google` + `discover_gmail_tokens()`, return `MultiGmailSource` or None
- [ ] Create `ntrp/integrations/calendar/`
  - Same structure, no notifier
  - `CALENDAR` integration
- [ ] Both are indexable, both report errors via `errors` attribute — keep that contract
- [ ] Delete `EmailSource`, `CalendarSource` Protocols
- [ ] Delete from `sources/registry.py`, `notifiers/service.py`, `tools/specs.py`
- [ ] Update tool calls: `get_source(EmailSource, "gmail")` → `get_client("gmail", MultiGmailSource)`
- [ ] Config field: `google` boolean stays in config, gmail/calendar integrations both check it
- [ ] Smoke test: Gmail read, calendar read, email send via notifier
- [ ] Commit

#### 3d. Telegram (notifier-only, no tools, no client) — 0.25 day

Tests the "integration with only a notifier" shape.

- [ ] Create `ntrp/integrations/telegram/`
- [ ] Move `ntrp/notifiers/telegram.py` → `notifier.py`
- [ ] `TELEGRAM` integration: `tools=[]`, `build=None` (no client), `notifier_class=TelegramNotifier`, `service_fields=[IntegrationField("telegram_bot_token", ...)]`
- [ ] Delete from `notifiers/service.py`, `SERVICE_KEY_FIELDS`
- [ ] Verify registry's `build` handling: when `build is None`, skip client creation but still expose notifier/service fields
- [ ] Smoke test: send test notification
- [ ] Commit

### Phase 4 — Bash notifier, MCP bridge (half day)

- [ ] `BashNotifier` — keep as generic "run a command" notifier, not tied to any integration. Move to `ntrp/notifiers/bash.py` stays, or create a special `ntrp/integrations/_builtin/` for notifiers with no home. Decide when we get there.
- [ ] `MCPManager.list_providers()` → returns `list[ToolProviderStatus]` with `kind="mcp"` for each connected/errored MCP server
- [ ] Extend `/settings/config` sources payload (or new `/integrations/providers` endpoint) to merge `integrations.list_providers() + mcp_manager.list_providers()`
- [ ] Sidebar renders both kinds, maybe with a small badge `[mcp]` for MCP ones
- [ ] Commit

### Phase 5 — Delete old scaffolding (half day)

All the stuff that existed only to bridge the old world.

- [ ] `ntrp/sources/` → delete entirely except `models.py` (RawItem) and `base.py` if anything still uses shared protocols (probably nothing after migration)
- [ ] `ntrp/sources/registry.py` → delete
- [ ] `ntrp/sources/base.py` → delete (protocols no longer needed)
- [ ] `ntrp/server/sources.py` `SourceManager` → delete, replaced by `IntegrationRegistry`
- [ ] `SERVICE_KEY_FIELDS` in `config.py` → computed at runtime from `ALL_INTEGRATIONS`
- [ ] `SERVICE_META` in `routers/settings.py` → computed at runtime from `ALL_INTEGRATIONS`
- [ ] `_NOTIFIER_CLASSES`, `NOTIFIER_FIELDS` in `notifiers/service.py` → computed at runtime from registry
- [ ] `ALL_TOOLS` in `tools/specs.py` → computed at runtime from registry + a small list of "builtin" tools that don't belong to any integration (bash, time, research, directives, background, automation, skills)
- [ ] `ToolContext.get_source` → delete (only `get_client` remains)
- [ ] Remove `requires = frozenset({"slack"})` from all tools — replaced by "tools only registered if integration's build succeeded"
- [ ] UI: delete hardcoded `SourcesSection` entries, loop over API response
- [ ] Run full test suite
- [ ] Commit

### Phase 6 — Documentation (half day)

- [ ] Write `ntrp/integrations/README.md` explaining:
  - What an Integration is
  - How to add one (step by step)
  - When to use native vs MCP
  - The `build` contract, the `Integration` fields
- [ ] Update project README if it mentions sources/tools/notifiers
- [ ] Delete `docs/integrations-refactor-plan.md` (this file) — superseded by the README
- [ ] Commit

---

## Builtin tools that don't belong to any integration

These stay as-is but need a home. I'll put them in a new `ntrp/integrations/_builtin/` module, registered as a synthetic `BUILTIN` integration with no config/notifier/client:

- `BashTool`
- `ReadFileTool`
- `CurrentTimeTool`
- `SetDirectivesTool`
- `NotifyTool`
- `ResearchTool`
- Background tools: `BackgroundTool`, `CancelBackgroundTaskTool`, `GetBackgroundResultTool`, `ListBackgroundTasksTool`
- Automation tools: `CreateAutomationTool`, `DeleteAutomationTool`, `ListAutomationsTool`, `GetAutomationResultTool`, `RunAutomationTool`, `UpdateAutomationTool`
- Memory tools: `RememberTool`, `RecallTool`, `ForgetTool` — or under a MEMORY integration
- `UseSkillTool`

These are core ntrp capabilities, not user-facing "things to connect." Keep them separate from the user-visible integrations list in the UI.

## Memory

Leave memory outside integrations for now. It has its own storage, consolidation loop, health model. Revisit after the refactor settles.

## Risk checklist

- [ ] **get_source callers:** grep all `get_source(` usages before deleting, make sure every one is migrated to `get_client(`
- [ ] **Tool `requires` field:** some tools use `requires = frozenset({"gmail"})` — make sure the registry's `active_tools()` logic correctly gates these
- [ ] **Indexable:** Obsidian, Gmail, Calendar currently implement `Indexable`. After the move, `runtime._sync_indexables()` still needs to find them via `isinstance(client, Indexable)`. Verify the protocol stays intact.
- [ ] **Error surfacing:** `SourceManager.errors` currently drives error messages in UI. `IntegrationRegistry` has its own `_errors` dict — make sure the same errors surface identically.
- [ ] **Multi-account sources (Gmail, Calendar):** Both wrap multiple accounts into one client. Ensure `_build` resolves all accounts correctly and `errors` attribute is preserved.
- [ ] **Config hot reload:** existing `reload_config()` calls `source_mgr.sync()` — replace with `integrations.sync()` + anything else that was bundled in the old sync.
- [ ] **Tests:** many tests mock `SourceManager` or `ctx.services["gmail"]` directly. Grep for these and update.

## Per-phase verification

Each phase ends with:

1. `uv run pytest tests/ -x -q` — all pass
2. Smoke test: start server, open UI, run a chat that exercises the migrated integration(s)
3. `git diff --stat main` sanity check — changes match expectations
4. Commit with a descriptive message

## Rollback plan

If any phase goes sideways:

- Phase 0-1: just `git reset --hard main` and rethink
- Phase 2+: revert the specific phase's commits; previous phases remain valid since they work in parallel with old code until Phase 5 deletes it
- Hard stop: if Phase 5 (deletion) reveals hidden coupling, don't delete — keep old scaffolding as dead code, add `# TODO delete after integrations land`, ship the working new path first

---

## Estimated effort

| Phase | Work |
|---|---|
| 0 | 30 min |
| 1 | 4-6 hours |
| 2 | 3-4 hours |
| 3a web | 2-3 hours |
| 3b obsidian | 2-3 hours |
| 3c gmail+calendar | 6-8 hours |
| 3d telegram | 1 hour |
| 4 mcp bridge | 3 hours |
| 5 deletion | 3 hours |
| 6 docs | 2 hours |

Total: ~3-4 working days if everything goes smoothly, ~1 week with debugging.
