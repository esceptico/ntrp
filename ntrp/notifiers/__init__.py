from collections.abc import Callable

from ntrp.config import Config
from ntrp.notifiers.base import Notifier
from ntrp.notifiers.bash import BashNotifier
from ntrp.notifiers.dispatcher import make_schedule_dispatcher
from ntrp.notifiers.email import EmailNotifier
from ntrp.notifiers.models import NotifierConfig
from ntrp.notifiers.telegram import TelegramNotifier

__all__ = [
    "BashNotifier",
    "EmailNotifier",
    "Notifier",
    "NotifierConfig",
    "TelegramNotifier",
    "create_notifier",
    "make_schedule_dispatcher",
]


def create_notifier(cfg: NotifierConfig, *, config: Config, gmail: Callable) -> Notifier:
    if cfg.type == "email":
        return EmailNotifier(
            gmail=gmail,
            from_account=cfg.config["from_account"],
            to_address=cfg.config["to_address"],
        )
    if cfg.type == "telegram":
        if not config.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
        return TelegramNotifier(
            token=config.telegram_bot_token,
            user_id=cfg.config["user_id"],
        )
    if cfg.type == "bash":
        return BashNotifier(command=cfg.config["command"])
    raise ValueError(f"Unknown notifier type: {cfg.type}")
