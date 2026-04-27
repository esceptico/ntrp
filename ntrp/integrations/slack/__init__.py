from ntrp.config import Config
from ntrp.integrations.base import Integration, IntegrationField
from ntrp.integrations.slack.client import SlackClient
from ntrp.integrations.slack.notifier import SlackNotifier
from ntrp.integrations.slack.tools import (
    SlackChannelTool,
    SlackChannelsTool,
    SlackDmsTool,
    SlackDmTool,
    SlackSearchTool,
    SlackThreadTool,
    SlackUserTool,
    SlackUsersTool,
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
    tools=[
        SlackSearchTool,
        SlackChannelTool,
        SlackThreadTool,
        SlackChannelsTool,
        SlackDmsTool,
        SlackDmTool,
        SlackUsersTool,
        SlackUserTool,
    ],
    notifier_class=SlackNotifier,
    build=_build,
)
