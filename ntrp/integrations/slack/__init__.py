from ntrp.config import Config
from ntrp.integrations.base import Integration, IntegrationField
from ntrp.integrations.slack.client import SlackClient
from ntrp.integrations.slack.notifier import SlackNotifier
from ntrp.integrations.slack.tools import (
    slack_channel_tool,
    slack_channels_tool,
    slack_dm_tool,
    slack_dms_tool,
    slack_search_tool,
    slack_thread_tool,
    slack_user_tool,
    slack_users_tool,
)


def _build(config: Config) -> SlackClient | None:
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
    tools={
        "slack_search": slack_search_tool,
        "slack_channel": slack_channel_tool,
        "slack_thread": slack_thread_tool,
        "slack_channels": slack_channels_tool,
        "slack_dms": slack_dms_tool,
        "slack_dm": slack_dm_tool,
        "slack_users": slack_users_tool,
        "slack_user": slack_user_tool,
    },
    notifier_class=SlackNotifier,
    build=_build,
)
