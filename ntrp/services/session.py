from datetime import UTC, datetime

from ntrp.context.models import SessionData, SessionState
from ntrp.context.store import SessionStore
from ntrp.core.compactor import compact_messages, compactable_range
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

    async def revert(self, session_id: str | None = None, turns: int = 1) -> dict | None:
        if not (data := await self.load(session_id)) or not data.messages:
            return None

        target_idx = None
        seen = 0
        for i in range(len(data.messages) - 1, -1, -1):
            if data.messages[i].get("role") == "user":
                seen += 1
                if seen >= turns:
                    target_idx = i
                    break

        if target_idx is None:
            return None

        raw = data.messages[target_idx]["content"]
        user_message = (
            raw
            if isinstance(raw, str)
            else "\n\n".join(
                b["text"] for b in raw if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
            )
            if isinstance(raw, list)
            else ""
        )
        reverted_count = len(data.messages) - target_idx
        data.messages = data.messages[:target_idx]
        metadata = {"last_input_tokens": data.last_input_tokens} if data.last_input_tokens else None
        await self.save(data.state, data.messages, metadata=metadata)
        return {"user_message": user_message, "reverted_count": reverted_count}

    async def permanently_delete(self, session_id: str) -> bool:
        return await self.store.permanently_delete_session(session_id)

    async def branch(self, session_id: str, name: str | None = None) -> SessionState | None:
        """Clone a session's messages into a new session, preserving context."""
        data = await self.load(session_id)
        if not data:
            return None
        new_state = self.create(name=name or (f"{data.state.name} (branch)" if data.state.name else None))
        new_state.auto_approve = set(data.state.auto_approve)
        new_state.skip_approvals = data.state.skip_approvals
        metadata = {"last_input_tokens": data.last_input_tokens} if data.last_input_tokens else None
        await self.save(new_state, list(data.messages), metadata=metadata)
        return new_state


async def compact_session(
    svc: SessionService,
    model: str,
    session_id: str | None = None,
    keep_ratio: float = 0.2,
    summary_max_tokens: int = 1500,
) -> dict:
    if not (data := await svc.load(session_id)):
        return {"status": "no_session", "message": "No active session to compact"}

    session_state = data.state
    messages = data.messages
    before_count = len(messages)
    before_tokens = data.last_input_tokens

    r = compactable_range(messages, keep_ratio=keep_ratio)
    if r is None:
        return {
            "status": "nothing_to_compact",
            "message": f"Nothing to compact ({before_count} messages)",
            "message_count": before_count,
        }
    msg_count = r[1] - r[0]

    new_messages = await compact_messages(
        messages,
        model,
        keep_ratio=keep_ratio,
        summary_max_tokens=summary_max_tokens,
    )

    if new_messages is not None:
        await svc.save(
            session_state,
            new_messages,
            metadata={"last_input_tokens": None},
        )
        return {
            "status": "compacted",
            "message": f"Compacted {before_count} → {len(new_messages)} messages ({msg_count} summarized)",
            "before_tokens": before_tokens,
            "before_messages": before_count,
            "after_messages": len(new_messages),
            "messages_compressed": msg_count,
        }

    return {
        "status": "already_optimal",
        "message": f"Context already optimal ({before_count} messages)",
        "message_count": before_count,
    }
