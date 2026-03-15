from typing import Self

import ntrp.database as database
from ntrp.automation.store import AutomationStore
from ntrp.config import Config
from ntrp.context.store import SessionStore
from ntrp.monitor.store import MonitorStateStore
from ntrp.notifiers.log_store import NotificationLogStore
from ntrp.notifiers.store import NotifierStore
from ntrp.services.session import SessionService


class Stores:
    """Database connection and all stores sharing it."""

    def __init__(
        self,
        conn: database.aiosqlite.Connection,
        sessions: SessionService,
        automations: AutomationStore,
        notifiers: NotifierStore,
        notifications: NotificationLogStore,
        monitor: MonitorStateStore,
    ):
        self.conn = conn
        self.sessions = sessions
        self.automations = automations
        self.notifiers = notifiers
        self.notifications = notifications
        self.monitor = monitor

    @classmethod
    async def connect(cls, config: Config) -> Self:
        config.db_dir.mkdir(exist_ok=True)
        conn = await database.connect(config.sessions_db_path)

        session_store = SessionStore(conn)
        await session_store.init_schema()

        automations = AutomationStore(conn)
        await automations.init_schema()

        notifiers = NotifierStore(conn)
        await notifiers.init_schema()

        notifications = NotificationLogStore(conn)
        await notifications.init_schema()

        monitor = MonitorStateStore(conn)
        await monitor.init_schema()

        return cls(
            conn=conn,
            sessions=SessionService(session_store),
            automations=automations,
            notifiers=notifiers,
            notifications=notifications,
            monitor=monitor,
        )

    async def close(self) -> None:
        await self.conn.close()
