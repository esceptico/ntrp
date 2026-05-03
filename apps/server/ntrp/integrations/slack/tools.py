from pydantic import BaseModel, Field

from ntrp.integrations.slack.client import SlackClient
from ntrp.tools.core import ToolResult, tool
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


SLACK_SEARCH_DESCRIPTION = (
    "Search Slack messages across the workspace using the Real-time Search API. "
    "Supports natural-language queries (semantic search) or keywords. "
    "Use scope='dms' to search only direct messages. "
    "Requires a Slack user token with granular search:read.* scopes."
)


async def slack_search(execution: ToolExecution, args: SlackSearchInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    channel_types = _SCOPE_MAP.get(args.scope.lower()) if args.scope else None
    results = await source.search_messages(args.query, limit=args.limit, channel_types=channel_types)
    if not results:
        return ToolResult(content=f"No Slack messages found for {args.query!r}", preview="0 results")
    return ToolResult(content=_format_messages(results), preview=f"{len(results)} messages")


class SlackChannelInput(BaseModel):
    channel: str = Field(description="Channel name (e.g. 'general' or '#general') or channel ID (e.g. 'C0123456789')")
    limit: int = Field(default=50, description="Max messages to fetch")


async def slack_channel(execution: ToolExecution, args: SlackChannelInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    results = await source.read_channel(args.channel, limit=args.limit)
    if not results:
        return ToolResult(content=f"No messages in #{args.channel}", preview="0 messages")
    return ToolResult(content=_format_messages(results), preview=f"{len(results)} messages")


class SlackThreadInput(BaseModel):
    message_id: str = Field(description="Message id (channel_id:ts) from a previous search/channel result")


SLACK_THREAD_DESCRIPTION = (
    "Read a Slack message and all its thread replies. Pass the message id from slack_search or slack_channel."
)


async def slack_thread(execution: ToolExecution, args: SlackThreadInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    content = await source.read_thread(args.message_id)
    if not content:
        return ToolResult(content=f"Message not found: {args.message_id}", preview="Not found")
    lines = content.count("\n") + 1
    return ToolResult(content=content, preview=f"Read {lines} lines")


class SlackChannelsInput(BaseModel):
    query: str | None = Field(default=None, description="Optional substring to filter channel names")
    limit: int = Field(default=50, description="Max channels to return")


async def slack_channels(execution: ToolExecution, args: SlackChannelsInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    results = await source.search_channels(args.query, limit=args.limit)
    if not results:
        return ToolResult(content="No matching channels", preview="0 channels")
    lines = [f"• #{c['name']}  ({c['id']})" for c in results]
    return ToolResult(content="\n".join(lines), preview=f"{len(results)} channels")


class SlackUsersInput(BaseModel):
    query: str | None = Field(default=None, description="Optional substring to filter by name, username, or email")
    limit: int = Field(default=50, description="Max users to return")


async def slack_users(execution: ToolExecution, args: SlackUsersInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    results = await source.search_users(args.query, limit=args.limit)
    if not results:
        return ToolResult(content="No matching users", preview="0 users")
    lines = []
    for user in results:
        line = f"• {user['name']}"
        if user.get("username"):
            line += f" (@{user['username']})"
        if user.get("title"):
            line += f" — {user['title']}"
        line += f"  id: {user['id']}"
        if user.get("email"):
            line += f"  {user['email']}"
        lines.append(line)
    return ToolResult(content="\n".join(lines), preview=f"{len(results)} users")


class SlackUserInput(BaseModel):
    user_id: str = Field(description="Slack user ID (e.g. U0123456789)")


async def slack_user(execution: ToolExecution, args: SlackUserInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    profile = await source.read_user(args.user_id)
    if not profile:
        return ToolResult(content=f"User not found: {args.user_id}", preview="Not found")
    lines = [f"{key}: {value}" for key, value in profile.items() if value]
    return ToolResult(content="\n".join(lines), preview=profile.get("name", args.user_id))


class SlackDmsInput(BaseModel):
    query: str | None = Field(default=None, description="Optional substring to filter by peer name or user id")
    limit: int = Field(default=50, description="Max DMs to return")


async def slack_dms(execution: ToolExecution, args: SlackDmsInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    dms = await source.list_dms(args.query, limit=args.limit)
    if not dms:
        return ToolResult(content="No open DMs", preview="0 DMs")
    lines = [f"• {dm['peer']}  (dm: {dm['channel_id']}, user: {dm['user_id']})" for dm in dms]
    return ToolResult(content="\n".join(lines), preview=f"{len(dms)} DMs")


class SlackDmInput(BaseModel):
    target: str = Field(description="DM channel id (D*), user id (U*/W*), or a name/handle to resolve to a DM.")
    limit: int = Field(default=50, description="Max messages to fetch")


SLACK_DM_DESCRIPTION = (
    "Read recent messages from a direct message conversation. "
    "Target can be a DM channel id, user id, or a name (fuzzy match via users.list)."
)


async def slack_dm(execution: ToolExecution, args: SlackDmInput) -> ToolResult:
    source = execution.ctx.get_client("slack", SlackClient)
    try:
        channel_id = await source.resolve_dm_target(args.target)
    except RuntimeError as e:
        return ToolResult(content=str(e), preview="Not found")
    results = await source.read_channel(channel_id, limit=args.limit)
    if not results:
        return ToolResult(content=f"No messages in DM with {args.target!r}", preview="0 messages")
    return ToolResult(content=_format_messages(results), preview=f"{len(results)} messages")


slack_search_tool = tool(
    display_name="SlackSearch",
    description=SLACK_SEARCH_DESCRIPTION,
    input_model=SlackSearchInput,
    requires={"slack"},
    execute=slack_search,
)

slack_channel_tool = tool(
    display_name="SlackChannel",
    description="Read recent message history from a Slack channel.",
    input_model=SlackChannelInput,
    requires={"slack"},
    execute=slack_channel,
)

slack_thread_tool = tool(
    display_name="SlackThread",
    description=SLACK_THREAD_DESCRIPTION,
    input_model=SlackThreadInput,
    requires={"slack"},
    execute=slack_thread,
)

slack_channels_tool = tool(
    display_name="SlackChannels",
    description="List Slack channels you can access. Optional query filters by name substring.",
    input_model=SlackChannelsInput,
    requires={"slack"},
    execute=slack_channels,
)

slack_dms_tool = tool(
    display_name="SlackDMs",
    description="List open Slack direct messages (1-on-1). Shows peer name and DM channel id.",
    input_model=SlackDmsInput,
    requires={"slack"},
    execute=slack_dms,
)

slack_dm_tool = tool(
    display_name="SlackDM",
    description=SLACK_DM_DESCRIPTION,
    input_model=SlackDmInput,
    requires={"slack"},
    execute=slack_dm,
)

slack_users_tool = tool(
    display_name="SlackUsers",
    description="Search Slack workspace members by name, username, or email.",
    input_model=SlackUsersInput,
    requires={"slack"},
    execute=slack_users,
)

slack_user_tool = tool(
    display_name="SlackUser",
    description="Read a Slack user's profile (name, email, title, status, timezone).",
    input_model=SlackUserInput,
    requires={"slack"},
    execute=slack_user,
)
