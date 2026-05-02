from collections import defaultdict
from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.registry import ToolRegistry

DEFERRED_SOURCES = frozenset(
    {"gmail", "calendar", "slack", "_automation", "_background", "_notifications", "_directives", "mcp"}
)

GROUP_ALIASES: dict[str, str] = {
    "email": "gmail",
    "emails": "gmail",
    "gmail": "gmail",
    "mail": "gmail",
    "calendar": "calendar",
    "cal": "calendar",
    "schedule": "calendar",
    "slack": "slack",
    "automations": "_automation",
    "automation": "_automation",
    "reminders": "_automation",
    "reminder": "_automation",
    "background": "_background",
    "backgrounds": "_background",
    "background_tasks": "_background",
    "background task": "_background",
    "notifications": "_notifications",
    "notification": "_notifications",
    "notify": "_notifications",
    "directives": "_directives",
    "directive": "_directives",
    "rules": "_directives",
    "behavior": "_directives",
    "mcp": "mcp",
}

GROUP_DESCRIPTIONS: dict[str, str] = {
    "gmail": "Search/list/read/send Gmail messages. Use for inbox, emails, Gmail, sending/replying, or communication history.",
    "calendar": "Search/create/edit/delete calendar events. Use for meetings, schedule, availability, appointments, reminders, or rescheduling.",
    "slack": "Search Slack and read channels, DMs, threads, and user profiles. Use for Slack messages, workspace history, coworkers, channels, DMs, or threads.",
    "_automation": "Create/list/update/delete/run autonomous scheduled or event-triggered tasks. Use for reminders, recurring checks, notifications, scheduled agents, or automation management.",
    "_background": "Spawn, inspect, cancel, or read background agents. Use for long-running research/work that should continue while the main chat moves on.",
    "_notifications": "Send a user-facing notification. Use when the user explicitly asks to be notified or an automation/background flow needs to alert them.",
    "_directives": "Update persistent behavior directives injected into the system prompt. Use when the user asks to change standing behavior, tone, or operating rules.",
    "mcp": "Connected MCP server tools. Use for external apps/servers not covered by core tools. Load by server, e.g. mcp:obsidian.",
}


def is_deferred_tool(name: str, registry: ToolRegistry) -> bool:
    source = registry.get_source(name)
    return source in DEFERRED_SOURCES


def _tool_summary(name: str, registry: ToolRegistry) -> str:
    tool = registry.get(name)
    if tool is None:
        return name
    desc = " ".join((tool.description or "").split())
    if len(desc) > 140:
        desc = desc[:137].rstrip() + "..."
    return f"{name} — {desc}" if desc else name


def _mcp_server_from_name(name: str) -> str | None:
    if not name.startswith("mcp_") or "__" not in name:
        return None
    return name.removeprefix("mcp_").split("__", 1)[0]


def _normalize_group(group: str) -> str:
    group = group.strip().lower()
    if group.startswith("mcp:"):
        return "mcp:" + group.split(":", 1)[1].strip()
    return GROUP_ALIASES.get(group, group)


@dataclass(frozen=True)
class DeferredCatalog:
    by_group: dict[str, list[str]]
    mcp_by_server: dict[str, list[str]]


def tool_schema_names(tools: list[dict]) -> set[str]:
    names: set[str] = set()
    for schema in tools:
        name = schema.get("function", {}).get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def build_deferred_catalog(
    registry: ToolRegistry,
    capabilities: frozenset[str],
    *,
    allowed_names: set[str] | None = None,
) -> DeferredCatalog:
    by_group: dict[str, list[str]] = defaultdict(list)
    mcp_by_server: dict[str, list[str]] = defaultdict(list)
    for name, tool_obj in registry.tools.items():
        if allowed_names is not None and name not in allowed_names:
            continue
        if not tool_obj.requires.issubset(capabilities):
            continue
        source = registry.get_source(name)
        if source not in DEFERRED_SOURCES:
            continue
        by_group[source].append(name)
        if source == "mcp":
            server = _mcp_server_from_name(name) or "default"
            mcp_by_server[server].append(name)
    return DeferredCatalog(
        by_group={k: sorted(v) for k, v in by_group.items()},
        mcp_by_server={k: sorted(v) for k, v in mcp_by_server.items()},
    )


def initial_loaded_tool_names(registry: ToolRegistry, capabilities: frozenset[str], *, mutates: bool | None = None) -> set[str]:
    names: set[str] = set()
    for name, tool_obj in registry.tools.items():
        if mutates is not None and tool_obj.mutates != mutates:
            continue
        if not tool_obj.requires.issubset(capabilities):
            continue
        if is_deferred_tool(name, registry):
            continue
        names.add(name)
    return names


def visible_tool_names(
    registry: ToolRegistry,
    capabilities: frozenset[str],
    loaded: set[str],
    *,
    allowed_names: set[str] | None = None,
) -> set[str]:
    names: set[str] = set()
    for name, tool_obj in registry.tools.items():
        if allowed_names is not None and name not in allowed_names:
            continue
        if not tool_obj.requires.issubset(capabilities):
            continue
        if is_deferred_tool(name, registry) and name not in loaded:
            continue
        names.add(name)
    return names


def build_deferred_tools_prompt(
    registry: ToolRegistry,
    capabilities: frozenset[str],
    *,
    allowed_names: set[str] | None = None,
) -> str | None:
    catalog = build_deferred_catalog(registry, capabilities, allowed_names=allowed_names)
    if not catalog.by_group:
        return None

    lines = [
        "Some integration/action tools are deferred to reduce prompt noise. Use `load_tools` before calling tools from these groups. Load tools proactively when the user's request needs the capability; do not ask whether to load them.",
        "",
    ]

    labels = {
        "gmail": "email",
        "_automation": "automations",
        "_background": "background",
        "_notifications": "notifications",
        "_directives": "directives",
    }
    for source in ("gmail", "calendar", "slack", "_automation", "_background", "_notifications", "_directives"):
        names = catalog.by_group.get(source)
        if not names:
            continue
        label = labels.get(source, source)
        lines.append(f'<deferred_tool_group name="{label}" load_group="{label}">')
        lines.append(GROUP_DESCRIPTIONS[source])
        lines.append("Tools: " + ", ".join(names) + ".")
        if any((registry.get(n) and registry.get(n).mutates) for n in names):
            lines.append("Write/action tools require approval after loading.")
        lines.append("</deferred_tool_group>")
        lines.append("")

    if catalog.mcp_by_server:
        lines.append('<deferred_tool_group name="mcp" load_group="mcp:<server>">')
        lines.append(GROUP_DESCRIPTIONS["mcp"])
        lines.append("Connected MCP servers:")
        for server, names in catalog.mcp_by_server.items():
            if len(names) <= 12:
                tool_part = ", ".join(names)
            else:
                tool_part = ", ".join(names[:10]) + f", ... ({len(names)} tools total)"
            lines.append(f'- {server}: load with `load_tools(group="mcp:{server}")`. Tools: {tool_part}.')
        lines.append("</deferred_tool_group>")

    return "\n".join(lines).strip()


def build_deferred_tools_prompt_for_schemas(
    registry: ToolRegistry,
    capabilities: frozenset[str],
    tools: list[dict],
) -> str | None:
    return build_deferred_tools_prompt(
        registry,
        capabilities,
        allowed_names=tool_schema_names(tools),
    )


def append_deferred_tools_prompt(
    system_prompt: str,
    registry: ToolRegistry,
    capabilities: frozenset[str],
    tools: list[dict],
    *,
    enabled: bool,
) -> str:
    if not enabled or "## DEFERRED TOOLS" in system_prompt:
        return system_prompt

    deferred_context = build_deferred_tools_prompt_for_schemas(registry, capabilities, tools)
    if not deferred_context:
        return system_prompt

    return f"{system_prompt.rstrip()}\n\n## DEFERRED TOOLS\n{deferred_context}"


class LoadToolsInput(BaseModel):
    group: str | None = Field(
        default=None,
        description="Deferred group to load, e.g. 'email', 'calendar', 'slack', 'automations', 'background', 'notifications', 'directives', or 'mcp:obsidian'.",
    )
    names: list[str] | None = Field(
        default=None,
        description="Exact deferred tool names to load, e.g. ['slack_search', 'slack_thread'].",
    )

    @model_validator(mode="after")
    def _require_group_or_names(self):
        if not self.group and not self.names:
            raise ValueError("Provide either group or names")
        return self


def _names_for_group(
    group: str,
    registry: ToolRegistry,
    capabilities: frozenset[str],
    *,
    allowed_names: set[str] | None = None,
) -> tuple[list[str], str | None]:
    normalized = _normalize_group(group)
    catalog = build_deferred_catalog(registry, capabilities, allowed_names=allowed_names)

    if normalized.startswith("mcp:"):
        server = normalized.split(":", 1)[1]
        names = catalog.mcp_by_server.get(server, [])
        if not names:
            servers = ", ".join(sorted(catalog.mcp_by_server)) or "none"
            return [], f"No MCP server {server!r}. Available MCP servers: {servers}."
        return names, None

    if normalized == "mcp":
        if len(catalog.mcp_by_server) == 1:
            return next(iter(catalog.mcp_by_server.values())), None
        servers = ", ".join(f"mcp:{s}" for s in sorted(catalog.mcp_by_server)) or "none"
        return [], f"Load MCP tools by server, e.g. group='mcp:obsidian'. Available MCP groups: {servers}."

    names = catalog.by_group.get(normalized, [])
    if not names:
        groups = ["email", "calendar", "slack", "automations", "background", "notifications", "directives"]
        groups.extend(f"mcp:{s}" for s in sorted(catalog.mcp_by_server))
        return [], "No deferred group {group!r}. Available groups: {groups}.".format(
            group=group,
            groups=", ".join(groups) or "none",
        )
    return names, None


def _dedupe(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


async def load_tools(execution: ToolExecution, args: LoadToolsInput) -> ToolResult:
    registry = execution.ctx.registry
    capabilities = execution.ctx.capabilities

    requested: list[str] = []
    errors: list[str] = []
    if args.group:
        group_names, err = _names_for_group(
            args.group,
            registry,
            capabilities,
            allowed_names=execution.ctx.run.allowed_tool_names,
        )
        requested.extend(group_names)
        if err:
            errors.append(err)
    if args.names:
        requested.extend(args.names)

    requested = _dedupe(requested)
    loaded_now: list[str] = []
    already_loaded: list[str] = []
    already_available: list[str] = []
    unknown: list[str] = []
    unavailable: list[str] = []
    not_allowed: list[str] = []

    for name in requested:
        tool_obj = registry.get(name)
        if tool_obj is None:
            unknown.append(name)
            continue
        if execution.ctx.run.allowed_tool_names is not None and name not in execution.ctx.run.allowed_tool_names:
            not_allowed.append(name)
            continue
        if not tool_obj.requires.issubset(capabilities):
            unavailable.append(name)
            continue
        if not is_deferred_tool(name, registry):
            already_available.append(name)
            continue
        if name in execution.ctx.run.loaded_tools:
            already_loaded.append(name)
            continue
        execution.ctx.run.loaded_tools.add(name)
        loaded_now.append(name)

    lines: list[str] = []
    if loaded_now:
        lines.append(f"Loaded {len(loaded_now)} deferred tool(s) for this run:")
        lines.extend(f"- {_tool_summary(name, registry)}" for name in loaded_now)
        lines.append("These tools are available on the next model step. Call them normally when needed.")
    if already_loaded:
        lines.append("Already loaded: " + ", ".join(already_loaded) + ".")
    if already_available:
        lines.append("Already available without loading: " + ", ".join(already_available) + ".")
    if unknown:
        lines.append("Unknown tool(s): " + ", ".join(unknown) + ".")
    if unavailable:
        lines.append("Unavailable due to missing capabilities: " + ", ".join(unavailable) + ".")
    if not_allowed:
        lines.append("Not allowed in this run: " + ", ".join(not_allowed) + ".")
    lines.extend(errors)

    if not lines:
        lines.append("No tools loaded.")

    is_error = bool(errors or unknown or unavailable or not_allowed) and not loaded_now and not already_loaded and not already_available
    preview = f"Loaded {len(loaded_now)}" if loaded_now else "No tools loaded"
    return ToolResult(content="\n".join(lines), preview=preview, is_error=is_error)


load_tools_tool = tool(
    display_name="Load Tools",
    description=(
        "Load deferred tool schemas into the current run by exact group or tool name. "
        "Use proactively when the user's request needs a deferred capability listed in the DEFERRED TOOLS prompt section. "
        "Loading tools does not execute them; it only makes them callable on the next model step. "
        "Examples: group='slack', group='email', group='calendar', group='automations', group='background', "
        "group='notifications', group='directives', group='mcp:obsidian', "
        "or names=['slack_search','slack_thread']."
    ),
    input_model=LoadToolsInput,
    execute=load_tools,
)
