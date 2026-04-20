from typing import Any

from pydantic import BaseModel, Field

from ntrp.integrations.slack.client import SlackClient
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.utils import truncate

_TEXT_TRUNCATE = 280
_DEFAULT_LIMIT = 20


def _format_messages(items: list, *, show_thread_hint: bool = True) -> str:
    lines = []
    for item in items:
        meta = item.metadata
        when = item.created_at.strftime("%Y-%m-%d %H:%M")
        cname = meta.get("channel_name", "")
        user = meta.get("user_name", "unknown")
        text = truncate(item.content or "(empty)", _TEXT_TRUNCATE)
        header = f"• [{when}] #{cname} — {user}"
        lines.append(header)
        lines.append(f"    {text}")
        suffix = []
        if show_thread_hint and meta.get("reply_count"):
            suffix.append(f"thread: {meta['reply_count']} replies")
        suffix.append(f"id: {item.source_id}")
        lines.append(f"    ({', '.join(suffix)})")
    return "\n".join(lines)


class SlackSearchInput(BaseModel):
    query: str = Field(description="Slack search query. Supports operators: from:@user in:#channel before:2024-01-01")
    limit: int = Field(default=_DEFAULT_LIMIT, description="Max results")
    scope: str | None = Field(
        default=None,
        description="Optional scope: 'dms' (DMs + group DMs only), 'channels' (public/private only), or None for all.",
    )


_SCOPE_MAP = {
    "dms": ["im", "mpim"],
    "channels": ["public_channel", "private_channel"],
    "all": None,
}


class SlackSearchTool(Tool):
    name = "slack_search"
    display_name = "SlackSearch"
    description = (
        "Search Slack messages across the workspace using the Real-time Search API. "
        "Supports natural-language queries (semantic search) or keywords. "
        "Use scope='dms' to search only direct messages. "
        "Requires a Slack user token with granular search:read.* scopes."
    )
    requires = frozenset({"slack"})
    input_model = SlackSearchInput

    async def execute(
        self,
        execution: ToolExecution,
        query: str,
        limit: int = _DEFAULT_LIMIT,
        scope: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        channel_types = _SCOPE_MAP.get(scope.lower()) if scope else None
        results = await source.search_messages(query, limit=limit, channel_types=channel_types)
        if not results:
            return ToolResult(content=f"No Slack messages found for {query!r}", preview="0 results")
        return ToolResult(content=_format_messages(results), preview=f"{len(results)} messages")


class SlackChannelInput(BaseModel):
    channel: str = Field(description="Channel name (e.g. 'general' or '#general') or channel ID (e.g. 'C0123456789')")
    limit: int = Field(default=50, description="Max messages to fetch")


class SlackChannelTool(Tool):
    name = "slack_channel"
    display_name = "SlackChannel"
    description = "Read recent message history from a Slack channel."
    requires = frozenset({"slack"})
    input_model = SlackChannelInput

    async def execute(self, execution: ToolExecution, channel: str, limit: int = 50, **kwargs: Any) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        results = await source.read_channel(channel, limit=limit)
        if not results:
            return ToolResult(content=f"No messages in #{channel}", preview="0 messages")
        return ToolResult(content=_format_messages(results), preview=f"{len(results)} messages")


class SlackThreadInput(BaseModel):
    message_id: str = Field(description="Message id (channel_id:ts) from a previous search/channel result")


class SlackThreadTool(Tool):
    name = "slack_thread"
    display_name = "SlackThread"
    description = "Read a Slack message and all its thread replies. Pass the message id from slack_search or slack_channel."
    requires = frozenset({"slack"})
    input_model = SlackThreadInput

    async def execute(self, execution: ToolExecution, message_id: str, **kwargs: Any) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        content = await source.read_thread(message_id)
        if not content:
            return ToolResult(content=f"Message not found: {message_id}", preview="Not found")
        lines = content.count("\n") + 1
        return ToolResult(content=content, preview=f"Read {lines} lines")


class SlackChannelsInput(BaseModel):
    query: str | None = Field(default=None, description="Optional substring to filter channel names")
    limit: int = Field(default=50, description="Max channels to return")


class SlackChannelsTool(Tool):
    name = "slack_channels"
    display_name = "SlackChannels"
    description = "List Slack channels you can access. Optional query filters by name substring."
    requires = frozenset({"slack"})
    input_model = SlackChannelsInput

    async def execute(self, execution: ToolExecution, query: str | None = None, limit: int = 50, **kwargs: Any) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        results = await source.search_channels(query, limit=limit)
        if not results:
            return ToolResult(content="No matching channels", preview="0 channels")
        lines = [f"• #{c['name']}  ({c['id']})" for c in results]
        return ToolResult(content="\n".join(lines), preview=f"{len(results)} channels")


class SlackUsersInput(BaseModel):
    query: str | None = Field(default=None, description="Optional substring to filter by name, username, or email")
    limit: int = Field(default=50, description="Max users to return")


class SlackUsersTool(Tool):
    name = "slack_users"
    display_name = "SlackUsers"
    description = "Search Slack workspace members by name, username, or email."
    requires = frozenset({"slack"})
    input_model = SlackUsersInput

    async def execute(self, execution: ToolExecution, query: str | None = None, limit: int = 50, **kwargs: Any) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        results = await source.search_users(query, limit=limit)
        if not results:
            return ToolResult(content="No matching users", preview="0 users")
        lines = []
        for u in results:
            line = f"• {u['name']}"
            if u.get("username"):
                line += f" (@{u['username']})"
            if u.get("title"):
                line += f" — {u['title']}"
            line += f"  id: {u['id']}"
            if u.get("email"):
                line += f"  {u['email']}"
            lines.append(line)
        return ToolResult(content="\n".join(lines), preview=f"{len(results)} users")


class SlackUserInput(BaseModel):
    user_id: str = Field(description="Slack user ID (e.g. U0123456789)")


class SlackUserTool(Tool):
    name = "slack_user"
    display_name = "SlackUser"
    description = "Read a Slack user's profile (name, email, title, status, timezone)."
    requires = frozenset({"slack"})
    input_model = SlackUserInput

    async def execute(self, execution: ToolExecution, user_id: str, **kwargs: Any) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        profile = await source.read_user(user_id)
        if not profile:
            return ToolResult(content=f"User not found: {user_id}", preview="Not found")
        lines = [f"{k}: {v}" for k, v in profile.items() if v]
        return ToolResult(content="\n".join(lines), preview=profile.get("name", user_id))


class SlackDmsInput(BaseModel):
    query: str | None = Field(default=None, description="Optional substring to filter by peer name or user id")
    limit: int = Field(default=50, description="Max DMs to return")


class SlackDmsTool(Tool):
    name = "slack_dms"
    display_name = "SlackDMs"
    description = "List open Slack direct messages (1-on-1). Shows peer name and DM channel id."
    requires = frozenset({"slack"})
    input_model = SlackDmsInput

    async def execute(
        self,
        execution: ToolExecution,
        query: str | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        dms = await source.list_dms(query, limit=limit)
        if not dms:
            return ToolResult(content="No open DMs", preview="0 DMs")
        lines = [f"• {d['peer']}  (dm: {d['channel_id']}, user: {d['user_id']})" for d in dms]
        return ToolResult(content="\n".join(lines), preview=f"{len(dms)} DMs")


class SlackDmInput(BaseModel):
    target: str = Field(
        description="DM channel id (D*), user id (U*/W*), or a name/handle to resolve to a DM."
    )
    limit: int = Field(default=50, description="Max messages to fetch")


class SlackDmTool(Tool):
    name = "slack_dm"
    display_name = "SlackDM"
    description = (
        "Read recent messages from a direct message conversation. "
        "Target can be a DM channel id, user id, or a name (fuzzy match via users.list)."
    )
    requires = frozenset({"slack"})
    input_model = SlackDmInput

    async def execute(
        self,
        execution: ToolExecution,
        target: str,
        limit: int = 50,
        **kwargs: Any,
    ) -> ToolResult:
        source = execution.ctx.get_client("slack", SlackClient)
        try:
            channel_id = await source.resolve_dm_target(target)
        except RuntimeError as e:
            return ToolResult(content=str(e), preview="Not found")
        results = await source.read_channel(channel_id, limit=limit)
        if not results:
            return ToolResult(content=f"No messages in DM with {target!r}", preview="0 messages")
        return ToolResult(content=_format_messages(results), preview=f"{len(results)} messages")
