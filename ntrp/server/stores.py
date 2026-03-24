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
    """Database connections and all stores sharing them.

    Uses two connections to sessions.db:
    - conn: for writes (single writer, SQLite requirement)
    - read_conn: for reads (concurrent with writes in WAL mode)
    """

    def __init__(
        self,
        conn: database.aiosqlite.Connection,
        read_conn: database.aiosqlite.Connection,
        sessions: SessionService,
        automations: AutomationStore,
        notifiers: NotifierStore,
        notifications: NotificationLogStore,
        monitor: MonitorStateStore,
    ):
        self.conn = conn
        self.read_conn = read_conn
        self.sessions = sessions
        self.automations = automations
        self.notifiers = notifiers
        self.notifications = notifications
        self.monitor = monitor

    @classmethod
    async def connect(cls, config: Config) -> Self:
        config.db_dir.mkdir(exist_ok=True)
        conn = await database.connect(config.sessions_db_path)
        read_conn = await database.connect(config.sessions_db_path, readonly=True)

        session_store = SessionStore(conn, read_conn)
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
            read_conn=read_conn,
            sessions=SessionService(session_store),
            automations=automations,
            notifiers=notifiers,
            notifications=notifications,
            monitor=monitor,
        )

    async def close(self) -> None:
        await self.read_conn.close()
        await self.conn.close()
