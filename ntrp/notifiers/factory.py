from typing import Any

from ntrp.notifiers.base import Notifier
from ntrp.notifiers.bash import BashNotifier
from ntrp.notifiers.email import EmailNotifier
from ntrp.notifiers.models import NotifierConfig
from ntrp.notifiers.telegram import TelegramNotifier

_NOTIFIER_CLASSES: list[type[Notifier]] = [EmailNotifier, TelegramNotifier, BashNotifier]
REGISTRY: dict[str, type[Notifier]] = {cls.channel: cls for cls in _NOTIFIER_CLASSES}


def create_notifier(cfg: NotifierConfig, runtime: Any) -> Notifier:
    cls = REGISTRY.get(cfg.type)
    if not cls:
        raise ValueError(f"Unknown notifier type: {cfg.type}")
    return cls.from_config(cfg.config, runtime)
