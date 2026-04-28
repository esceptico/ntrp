"""Tests for chat extraction via the extraction handler."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

import ntrp.database as database
import ntrp.llm.models as llm_models
from ntrp.automation.store import AutomationStore
from ntrp.config import Config
from ntrp.llm.models import EmbeddingModel, Provider
from ntrp.memory.extraction_handler import create_chat_extraction_handler
from ntrp.memory.facts import FactMemory
from ntrp.settings import hash_api_key
from tests.conftest import TEST_EMBEDDING_DIM, mock_embedding


async def _mock_embed_one(text: str):
    return mock_embedding(text)


def _make_messages(n: int) -> tuple[dict, ...]:
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"Message {i}"})
    return tuple(msgs)


@pytest_asyncio.fixture
async def memory(tmp_path: Path, monkeypatch) -> AsyncGenerator[FactMemory]:
    import ntrp.settings

    monkeypatch.setattr(ntrp.settings, "NTRP_DIR", tmp_path / "db")
    monkeypatch.setattr(ntrp.config, "NTRP_DIR", tmp_path / "db")

    test_emb = EmbeddingModel("test-embedding", Provider.OPENAI, TEST_EMBEDDING_DIM)
    monkeypatch.setitem(llm_models._embedding_models, "test-embedding", test_emb)

    config = Config(
        ntrp_dir=tmp_path / "db",
        vault_path=tmp_path / "vault",
        openai_api_key="test-key",
        api_key_hash=hash_api_key("test-api-key"),
        memory=True,
        embedding_model="test-embedding",
        memory_model="gemini-3-flash-preview",
        chat_model="gemini-3-flash-preview",
        exa_api_key=None,
    )
    config.db_dir.mkdir(parents=True, exist_ok=True)

    mem = await FactMemory.create(
        db_path=config.memory_db_path,
        embedding=config.embedding,
        model=config.memory_model,
    )
    mem.embedder.embed_one = _mock_embed_one
    yield mem
    await mem.close()


@pytest_asyncio.fixture
async def automation_store(tmp_path: Path) -> AsyncGenerator[AutomationStore]:
    conn = await database.connect(tmp_path / "automation.db")
    store = AutomationStore(conn)
    await store.init_schema()
    yield store
    await conn.close()


class TestExtractionCountTrigger:
    """Extraction fires on count trigger with session context."""

    @pytest.mark.asyncio
    async def test_count_trigger_extracts(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        mock_extract = AsyncMock(return_value=["User likes Python"])
        with patch("ntrp.memory.extraction_handler.extract_from_chat", mock_extract):
            msgs = _make_messages(10)
            result = await handler(
                {
                    "trigger_type": "count",
                    "session_id": "sess-1",
                    "messages": list(msgs),
                }
            )

            mock_extract.assert_called_once()
            assert result is not None
            assert "1 facts" in result

    @pytest.mark.asyncio
    async def test_count_trigger_no_facts(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.extraction_handler.extract_from_chat", mock_extract):
            result = await handler(
                {
                    "trigger_type": "count",
                    "session_id": "sess-1",
                    "messages": list(_make_messages(4)),
                }
            )

            assert result is None


class TestExtractionIdleTrigger:
    """Extraction fires on idle trigger for all pending sessions."""

    @pytest.mark.asyncio
    async def test_idle_extracts_pending(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        # Simulate RunCompleted events accumulating pending messages
        await automation_store.record_chat_extraction_activity("sess-1", _make_messages(6), datetime.now(UTC))
        await automation_store.record_chat_extraction_activity("sess-2", _make_messages(4), datetime.now(UTC))

        mock_extract = AsyncMock(return_value=["Fact from idle"])
        with patch("ntrp.memory.extraction_handler.extract_from_chat", mock_extract):
            await handler({"trigger_type": "idle", "idle_minutes": 5})

            # Should have extracted from both pending sessions
            assert mock_extract.call_count == 2

    @pytest.mark.asyncio
    async def test_idle_no_pending(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.extraction_handler.extract_from_chat", mock_extract):
            result = await handler({"trigger_type": "idle", "idle_minutes": 5})

            mock_extract.assert_not_called()
            assert result is None


class TestExtractionCursor:
    """Cursor tracks which messages have been processed."""

    @pytest.mark.asyncio
    async def test_cursor_advances(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        mock_extract = AsyncMock(return_value=[])
        with patch("ntrp.memory.extraction_handler.extract_from_chat", mock_extract):
            # First extraction: 10 messages
            msgs1 = list(_make_messages(10))
            await handler(
                {
                    "trigger_type": "count",
                    "session_id": "sess-1",
                    "messages": msgs1,
                }
            )

            # Second extraction: 20 messages (10 old + 10 new)
            msgs2 = list(_make_messages(20))
            await handler(
                {
                    "trigger_type": "count",
                    "session_id": "sess-1",
                    "messages": msgs2,
                }
            )

            # Second call should get context window + new messages
            second_call_msgs = mock_extract.call_args_list[1][0][0]
            # context_start = max(0, 10 - 10) = 0
            # window = msgs2[0:] = all 20 messages
            assert len(second_call_msgs) == 20


class TestExtractionRemember:
    """Extracted facts are stored via remember()."""

    @pytest.mark.asyncio
    async def test_facts_stored(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        mock_extract = AsyncMock(return_value=["User prefers dark mode", "User works at Acme"])
        with patch("ntrp.memory.extraction_handler.extract_from_chat", mock_extract):
            await handler(
                {
                    "trigger_type": "count",
                    "session_id": "sess-1",
                    "messages": list(_make_messages(6)),
                }
            )

        facts = await memory.facts.list_recent(limit=10)
        texts = {f.text for f in facts}
        assert "User prefers dark mode" in texts
        assert "User works at Acme" in texts


class TestExtractionSkips:
    """Handler returns None for unknown trigger types or missing context."""

    @pytest.mark.asyncio
    async def test_skips_no_context(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        result = await handler(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_unknown_trigger(self, memory: FactMemory, automation_store: AutomationStore):
        handler = create_chat_extraction_handler(memory, automation_store)

        result = await handler({"trigger_type": "unknown"})
        assert result is None
