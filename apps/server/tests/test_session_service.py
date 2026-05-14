import asyncio
from datetime import UTC, datetime

import pytest

from ntrp.context.models import SessionState
from ntrp.services.session import SessionService


class _SlowStore:
    def __init__(self):
        self.in_save = False
        self.overlapped = False

    async def save_session(self, session_state, messages, metadata=None):
        if self.in_save:
            self.overlapped = True
        self.in_save = True
        await asyncio.sleep(0.01)
        self.in_save = False


@pytest.mark.asyncio
async def test_session_service_serializes_saves_for_same_session():
    store = _SlowStore()
    service = SessionService(store)
    state = SessionState(session_id="sess-1", started_at=datetime.now(UTC))

    await asyncio.gather(
        service.save(state, [{"role": "user", "content": "one"}]),
        service.save(state, [{"role": "user", "content": "two"}]),
    )

    assert store.overlapped is False
