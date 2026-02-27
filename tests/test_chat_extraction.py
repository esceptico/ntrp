"""Tests for per-turn memory extraction via RunCompleted events."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from ntrp.channel import Channel
from ntrp.constants import EXTRACTION_CONTEXT_MESSAGES, EXTRACTION_EVERY_N_TURNS
from ntrp.events.internal import RunCompleted
from ntrp.memory.service import MemoryService
from ntrp.usage import Usage
from tests.conftest import TEST_EMBEDDING_DIM, mock_embedding

import ntrp.config
import ntrp.llm.models as llm_models
from ntrp.config import Config
from ntrp.llm.models import EmbeddingModel, Provider
from ntrp.memory.facts import FactMemory


async def _mock_embed_one(text: str):
    return mock_embedding(text)


def _make_messages(n: int) -> tuple[dict, ...]:
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"Message {i}"})
    return tuple(msgs)


def _make_event(session_id: str, messages: tuple[dict, ...], result: str = "done") -> RunCompleted:
    return RunCompleted(
        run_id=f"run-{id(messages)}",
        session_id=session_id,
        messages=messages,
        usage=Usage(),
        result=result,
    )


@pytest_asyncio.fixture
async def memory(tmp_path: Path, monkeypatch) -> AsyncGenerator[FactMemory]:
    monkeypatch.setattr(ntrp.config, "NTRP_DIR", tmp_path / "db")

    test_emb = EmbeddingModel("test-embedding", Provider.OPENAI, TEST_EMBEDDING_DIM)
    monkeypatch.setitem(llm_models._embedding_models, "test-embedding", test_emb)

    config = Config(
        vault_path=tmp_path / "vault",
        openai_api_key="test-key",
        api_key="test-api-key",
        memory=True,
        embedding_model="test-embedding",
        memory_model="gemini-3-flash-preview",
        chat_model="gemini-3-flash-preview",
        browser=None,
        exa_api_key=None,
    )
    config.db_dir.mkdir(parents=True, exist_ok=True)

    mem = await FactMemory.create(
        db_path=config.memory_db_path,
        embedding=config.embedding,
        extraction_model=config.memory_model,
        channel=Channel(),
    )
    mem.embedder.embed_one = _mock_embed_one
    yield mem
    await mem.close()


class TestExtractionTurnCounter:
    """Extraction only fires every N turns."""

    @pytest.mark.asyncio
    async def test_skips_before_n_turns(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=["User likes Python"])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            for i in range(EXTRACTION_EVERY_N_TURNS - 1):
                event = _make_event("sess-1", _make_messages(4))
                await svc._on_run_completed(event)

            mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_fires_at_n_turns(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=["User likes Python"])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            for i in range(EXTRACTION_EVERY_N_TURNS):
                event = _make_event("sess-1", _make_messages(4))
                await svc._on_run_completed(event)

            mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_fires_every_n_turns(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            for i in range(EXTRACTION_EVERY_N_TURNS * 3):
                event = _make_event("sess-1", _make_messages(4))
                await svc._on_run_completed(event)

            assert mock_extract.call_count == 3


class TestExtractionCursor:
    """Cursor tracks which messages have been processed."""

    @pytest.mark.asyncio
    async def test_cursor_advances(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            # First batch: 10 messages
            msgs1 = _make_messages(10)
            for i in range(EXTRACTION_EVERY_N_TURNS):
                await svc._on_run_completed(_make_event("sess-1", msgs1))

            assert svc._cursors["sess-1"] == 10

            # Second batch: 20 messages (10 old + 10 new)
            msgs2 = _make_messages(20)
            for i in range(EXTRACTION_EVERY_N_TURNS):
                await svc._on_run_completed(_make_event("sess-1", msgs2))

            assert svc._cursors["sess-1"] == 20

            # Second call should get context window + new messages
            second_call_msgs = mock_extract.call_args_list[1][0][0]
            # context_start = max(0, 10 - EXTRACTION_CONTEXT_MESSAGES) = 0
            # window = msgs2[0:] = all 20 messages
            assert len(second_call_msgs) == 20

    @pytest.mark.asyncio
    async def test_context_window_slicing(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            # First batch: 30 messages
            msgs1 = _make_messages(30)
            for i in range(EXTRACTION_EVERY_N_TURNS):
                await svc._on_run_completed(_make_event("sess-1", msgs1))

            assert svc._cursors["sess-1"] == 30

            # Second batch: 50 messages (30 old + 20 new)
            msgs2 = _make_messages(50)
            for i in range(EXTRACTION_EVERY_N_TURNS):
                await svc._on_run_completed(_make_event("sess-1", msgs2))

            # context_start = max(0, 30 - 10) = 20
            # window = msgs2[20:] = 30 messages (10 context + 20 new)
            second_call_msgs = mock_extract.call_args_list[1][0][0]
            assert len(second_call_msgs) == 30


class TestExtractionSkips:
    """Extraction is skipped for cancelled runs and empty messages."""

    @pytest.mark.asyncio
    async def test_skips_cancelled_run(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            for i in range(EXTRACTION_EVERY_N_TURNS):
                event = RunCompleted(
                    run_id="run-1",
                    session_id="sess-1",
                    messages=_make_messages(4),
                    usage=Usage(),
                    result=None,  # cancelled
                )
                await svc._on_run_completed(event)

            mock_extract.assert_not_called()
            # Turn counter should not have incremented
            assert svc._turn_counts.get("sess-1", 0) == 0

    @pytest.mark.asyncio
    async def test_skips_empty_messages(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            for i in range(EXTRACTION_EVERY_N_TURNS):
                event = _make_event("sess-1", ())
                await svc._on_run_completed(event)

            mock_extract.assert_not_called()


class TestExtractionRemember:
    """Extracted facts are stored via remember()."""

    @pytest.mark.asyncio
    async def test_facts_stored(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=["User prefers dark mode", "User works at Acme"])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            for i in range(EXTRACTION_EVERY_N_TURNS):
                event = _make_event("sess-1", _make_messages(6))
                await svc._on_run_completed(event)

        facts = await memory.facts.list_recent(limit=10)
        texts = {f.text for f in facts}
        assert "User prefers dark mode" in texts
        assert "User works at Acme" in texts

    @pytest.mark.asyncio
    async def test_independent_sessions(self, memory: FactMemory):
        channel = Channel()
        svc = MemoryService(memory, channel)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.service.extract_from_chat", mock_extract):
            # Interleave two sessions, each below threshold
            for i in range(EXTRACTION_EVERY_N_TURNS - 1):
                await svc._on_run_completed(_make_event("sess-1", _make_messages(4)))
                await svc._on_run_completed(_make_event("sess-2", _make_messages(4)))

            mock_extract.assert_not_called()

            # Push sess-1 to threshold
            await svc._on_run_completed(_make_event("sess-1", _make_messages(4)))
            assert mock_extract.call_count == 1

            # sess-2 still below
            assert svc._turn_counts["sess-2"] == EXTRACTION_EVERY_N_TURNS - 1
