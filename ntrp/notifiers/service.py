import re
from collections.abc import Callable
from datetime import UTC, datetime

from ntrp.notifiers.base import Notifier
from ntrp.notifiers.models import NotifierConfig
from ntrp.notifiers.store import NotifierStore
from ntrp.schedule.store import ScheduleStore

VALID_TYPES = {"email", "telegram", "bash"}
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")


class NotifierService:
    def __init__(
        self,
        store: NotifierStore,
        schedule_store: ScheduleStore | None,
        notifiers: dict[str, Notifier],
        rebuild_fn: Callable,
        get_gmail: Callable,
    ):
        self.store = store
        self.schedule_store = schedule_store
        self.notifiers = notifiers
        self.rebuild_fn = rebuild_fn
        self.get_gmail = get_gmail

    def validate_config(self, notifier_type: str, config: dict) -> None:
        if notifier_type not in VALID_TYPES:
            raise ValueError(f"Invalid notifier type: {notifier_type}")

        if notifier_type == "email":
            if not config.get("from_account"):
                raise ValueError("from_account is required")
            if not config.get("to_address"):
                raise ValueError("to_address is required")
            gmail = self.get_gmail()
            if gmail:
                accounts = gmail.list_accounts()
                if config["from_account"] not in accounts:
                    raise ValueError(f"Unknown Gmail account: {config['from_account']}")
        elif notifier_type == "telegram":
            if not config.get("user_id"):
                raise ValueError("user_id is required")
        elif notifier_type == "bash":
            if not config.get("command"):
                raise ValueError("command is required")

    async def create(self, name: str, notifier_type: str, config: dict) -> NotifierConfig:
        if not NAME_RE.match(name):
            raise ValueError("Name must be alphanumeric with hyphens")

        existing = await self.store.get(name)
        if existing:
            raise ValueError(f"Notifier '{name}' already exists")

        self.validate_config(notifier_type, config)

        cfg = NotifierConfig(
            name=name,
            type=notifier_type,
            config=config,
            created_at=datetime.now(UTC),
        )
        await self.store.save(cfg)
        await self.rebuild_fn()
        return cfg

    async def update(self, name: str, new_config: dict, new_name: str | None = None) -> NotifierConfig:
        existing = await self.store.get(name)
        if not existing:
            raise KeyError(f"Notifier '{name}' not found")

        self.validate_config(existing.type, new_config)

        if new_name and new_name != name:
            if not NAME_RE.match(new_name):
                raise ValueError("Name must be alphanumeric with hyphens")
            conflict = await self.store.get(new_name)
            if conflict:
                raise ValueError(f"Notifier '{new_name}' already exists")
            await self.store.delete(name)
            existing.name = new_name

        existing.config = new_config
        await self.store.save(existing)
        await self.rebuild_fn()
        return existing

    async def delete(self, name: str) -> None:
        deleted = await self.store.delete(name)
        if not deleted:
            raise KeyError(f"Notifier '{name}' not found")

        if self.schedule_store:
            tasks = await self.schedule_store.list_all()
            for task in tasks:
                if name in task.notifiers:
                    new_notifiers = [n for n in task.notifiers if n != name]
                    await self.schedule_store.set_notifiers(task.task_id, new_notifiers)

        await self.rebuild_fn()

    async def test(self, name: str) -> None:
        notifier = self.notifiers.get(name)
        if not notifier:
            raise KeyError(f"Notifier '{name}' not found")

        await notifier.send("Hello from ntrp", "Test notification — if you see this, it works!")
