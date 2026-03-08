from datetime import UTC, datetime

from ntrp.context.models import SessionData, SessionState
from ntrp.context.store import SessionStore
from ntrp.logging import get_logger

_logger = get_logger(__name__)


class SessionService:
    def __init__(self, store: SessionStore):
        self.store = store

    def create(self, name: str | None = None) -> SessionState:
        now = datetime.now(UTC)
        return SessionState(
            session_id=f"{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond // 1000:03d}",
            started_at=now,
            name=name,
        )

    async def load(self, session_id: str | None = None) -> SessionData | None:
        try:
            sid = session_id or await self.store.get_latest_id()
            if not sid:
                return None
            return await self.store.load_session(sid)
        except Exception as e:
            _logger.warning("Failed to load session %s: %s", session_id or "latest", e)
            return None

    async def save(
        self,
        session_state: SessionState,
        messages: list[dict],
        metadata: dict | None = None,
    ) -> None:
        try:
            session_state.last_activity = datetime.now(UTC)
            await self.store.save_session(session_state, messages, metadata=metadata)
        except Exception as e:
            _logger.warning("Failed to save session: %s", e)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return await self.store.list_sessions(limit=limit)

    async def rename(self, session_id: str, name: str) -> bool:
        return await self.store.update_session_name(session_id, name)

    async def archive(self, session_id: str) -> bool:
        return await self.store.archive_session(session_id)

    async def restore(self, session_id: str) -> bool:
        return await self.store.restore_session(session_id)

    async def list_archived(self, limit: int = 20) -> list[dict]:
        return await self.store.list_archived_sessions(limit=limit)

    async def revert(self, session_id: str | None = None) -> dict | None:
        data = await self.load(session_id)
        if not data or not data.messages:
            return None

        last_user_idx = None
        for i in range(len(data.messages) - 1, -1, -1):
            if data.messages[i].get("role") == "user":
                last_user_idx = i
                break

        if last_user_idx is None:
            return None

        user_message = data.messages[last_user_idx]["content"]
        reverted_count = len(data.messages) - last_user_idx
        data.messages = data.messages[:last_user_idx]
        metadata = {"last_input_tokens": data.last_input_tokens} if data.last_input_tokens else None
        await self.save(data.state, data.messages, metadata=metadata)
        return {"user_message": user_message, "reverted_count": reverted_count}

    async def permanently_delete(self, session_id: str) -> bool:
        return await self.store.permanently_delete_session(session_id)
