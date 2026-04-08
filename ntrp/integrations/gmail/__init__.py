from ntrp.config import Config
from ntrp.integrations.base import Integration
from ntrp.integrations.gmail.client import MultiGmailSource
from ntrp.integrations.gmail.notifier import EmailNotifier
from ntrp.integrations.gmail.tools import EmailsTool, ReadEmailTool, SendEmailTool
from ntrp.integrations.google_auth.auth import discover_gmail_tokens


def _build(config: Config) -> MultiGmailSource | None:
    if not config.google:
        return None
    token_paths = discover_gmail_tokens()
    if not token_paths:
        return None
    source = MultiGmailSource(token_paths=token_paths, days_back=config.gmail_days)
    return source if source.sources else None


GMAIL = Integration(
    id="gmail",
    label="Gmail",
    tools=[EmailsTool, ReadEmailTool, SendEmailTool],
    notifier_class=EmailNotifier,
    build=_build,
)
