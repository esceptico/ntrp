import asyncio
from datetime import UTC, datetime
from typing import Literal

from ntrp.context.models import SessionData, SessionState
from ntrp.context.store import SessionStore
from ntrp.core.compactor import compact_messages, compactable_range
from ntrp.logging import get_logger

_logger = get_logger(__name__)


class SessionService:
    def __init__(self, store: SessionStore):
        self.store = store
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    def create(
        self,
        name: str | None = None,
        session_type: Literal["chat", "channel"] = "chat",
        origin_automation_id: str | None = None,
    ) -> SessionState:
        now = datetime.now(UTC)
        return SessionState(
            session_id=f"{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond // 1000:03d}",
            started_at=now,
            name=name,
            session_type=session_type,
            origin_automation_id=origin_automation_id,
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
            async with self._lock_for(session_state.session_id):
                await self.store.save_session(session_state, messages, metadata=metadata)
        except Exception as e:
            _logger.warning("Failed to save session: %s", e)

    async def save_progress(self, session_state: SessionState, messages: list[dict]) -> None:
        """Mid-run checkpoint — upserts messages, leaves metadata alone."""
        try:
            session_state.last_activity = datetime.now(UTC)
            async with self._lock_for(session_state.session_id):
                await self.store.update_progress(session_state, messages)
        except Exception as e:
            _logger.warning("Failed to save mid-run progress: %s", e)

    async def record_chat_run_started(self, run_id: str, session_id: str, metadata: dict | None = None) -> None:
        try:
            await self.store.record_chat_run_started(run_id, session_id, metadata=metadata)
        except Exception as e:
            _logger.warning("Failed to record chat run start: %s", e)

    async def record_chat_run_status(
        self,
        run_id: str,
        status: str,
        *,
        stop_reason: str | None = None,
        last_seq: int | None = None,
    ) -> None:
        try:
            await self.store.record_chat_run_status(
                run_id,
                status,
                stop_reason=stop_reason,
                last_seq=last_seq,
            )
        except Exception as e:
            _logger.warning("Failed to record chat run status: %s", e)

    async def record_chat_queued_message(
        self,
        *,
        client_id: str,
        session_id: str,
        run_id: str,
        message: dict,
        enqueued_seq: int | None = None,
    ) -> None:
        try:
            await self.store.record_chat_queued_message(
                client_id=client_id,
                session_id=session_id,
                run_id=run_id,
                message=message,
                enqueued_seq=enqueued_seq,
            )
        except Exception as e:
            _logger.warning("Failed to record queued chat message: %s", e)

    async def mark_chat_queued_message_ingested(self, client_id: str, ingested_seq: int | None = None) -> None:
        try:
            await self.store.mark_chat_queued_message_ingested(client_id, ingested_seq=ingested_seq)
        except Exception as e:
            _logger.warning("Failed to mark queued chat message ingested: %s", e)

    async def mark_chat_queued_message_cancelled(self, client_id: str) -> None:
        try:
            await self.store.mark_chat_queued_message_cancelled(client_id)
        except Exception as e:
            _logger.warning("Failed to mark queued chat message cancelled: %s", e)

    async def record_chat_compaction(
        self,
        *,
        compaction_id: str,
        session_id: str,
        boundary_seq: int,
        messages_before: int,
        messages_after: int,
    ) -> None:
        try:
            await self.store.record_chat_compaction(
                compaction_id=compaction_id,
                session_id=session_id,
                boundary_seq=boundary_seq,
                messages_before=messages_before,
                messages_after=messages_after,
            )
        except Exception as e:
            _logger.warning("Failed to record chat compaction: %s", e)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return await self.store.list_sessions(limit=limit)

    async def list_messages(
        self,
        session_id: str,
        limit: int = 100,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
        around_seq: int | None = None,
    ) -> dict:
        return await self.store.list_session_messages(
            session_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
            around_seq=around_seq,
        )

    async def list_episodes(self, session_id: str, limit: int = 100) -> list[dict]:
        return await self.store.list_session_episodes(session_id, limit=limit)

    async def rename(self, session_id: str, name: str) -> bool:
        return await self.store.update_session_name(session_id, name)

    async def archive(self, session_id: str) -> bool:
        return await self.store.archive_session(session_id)

    async def restore(self, session_id: str) -> bool:
        return await self.store.restore_session(session_id)

    async def list_archived(self, limit: int = 20) -> list[dict]:
        return await self.store.list_archived_sessions(limit=limit)

    async def revert(
        self,
        session_id: str | None = None,
        turns: int = 1,
        message_id: str | None = None,
    ) -> dict | None:
        if not (data := await self.load(session_id)) or not data.messages:
            return None

        target_idx: int | None = None
        if message_id is not None:
            for i, msg in enumerate(data.messages):
                if msg.get("client_id") == message_id or msg.get("message_id") == message_id:
                    target_idx = i
                    break
        else:
            seen = 0
            for i in range(len(data.messages) - 1, -1, -1):
                if data.messages[i].get("role") == "user":
                    seen += 1
                    if seen >= turns:
                        target_idx = i
                        break

        if target_idx is None:
            return None

        target_message = data.messages[target_idx]
        target_ref = target_message.get("message_id") or target_message.get("client_id")
        raw = target_message["content"]
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
        await self.store.delete_session_messages_from(
            data.state.session_id,
            message_id=target_ref if isinstance(target_ref, str) else None,
            seq=target_idx if not isinstance(target_ref, str) else None,
        )
        return {"user_message": user_message, "reverted_count": reverted_count}

    async def permanently_delete(self, session_id: str) -> bool:
        return await self.store.permanently_delete_session(session_id)

    async def branch(
        self,
        session_id: str,
        name: str | None = None,
        up_to_message_id: str | None = None,
        from_end_index: int | None = None,
    ) -> SessionState | None:
        """Clone a session's messages into a new session, preserving context.

        Either pin-point arg picks the truncation point (and a trailing
        tool-message run is kept so the cloned context is valid):

        - `up_to_message_id`: the saved `client_id` of the assistant message
          to include. Preferred — works without positional math.
        - `from_end_index`: legacy positional fallback for sessions whose
          messages were persisted before stable ids were introduced. 0 = the
          last message, 1 = the second-to-last, …
        """
        data = await self.load(session_id)
        if not data:
            return None

        messages = list(data.messages)
        target_idx: int | None = None

        if up_to_message_id is not None:
            for i, msg in enumerate(messages):
                if msg.get("client_id") == up_to_message_id or msg.get("message_id") == up_to_message_id:
                    target_idx = i
                    break
            if target_idx is None:
                return None
        elif from_end_index is not None:
            if from_end_index < 0 or from_end_index >= len(messages):
                return None
            target_idx = len(messages) - 1 - from_end_index

        if target_idx is not None:
            end = target_idx + 1
            while end < len(messages) and messages[end].get("role") == "tool":
                end += 1
            messages = messages[:end]

        new_state = self.create(name=name or (f"{data.state.name} (branch)" if data.state.name else None))
        new_state.auto_approve = set(data.state.auto_approve)
        new_state.skip_approvals = data.state.skip_approvals
        metadata = {"last_input_tokens": data.last_input_tokens} if data.last_input_tokens else None
        await self.save(new_state, messages, metadata=metadata)
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
