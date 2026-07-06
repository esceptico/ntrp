from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore
from ntrp.services.session import SessionService


@pytest_asyncio.fixture
async def session_service(tmp_path: Path):
    conn = await database.connect(tmp_path / "sessions.db")
    s = SessionStore(conn)
    await s.init_schema()
    yield SessionService(s)
    await conn.close()


def test_session_state_carries_slice_key():
    s = SessionState(session_id="s1", started_at=datetime.now(UTC), slice_key="o-1a")
    assert s.slice_key == "o-1a"


@pytest.mark.asyncio
async def test_provision_persists_slice_key(session_service):
    state = await session_service.provision(name="counsel", slice_key="o-1a")
    loaded = await session_service.load(state.session_id)
    assert loaded.state.slice_key == "o-1a"
