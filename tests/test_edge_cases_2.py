"""More edge cases — targeting recent changes and risky paths."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import BaseModel

import ntrp.database as database
from ntrp.agent import Agent
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore
from ntrp.memory.facts import SessionMemory
from ntrp.memory.formatting import model_memory_context
from ntrp.memory.models import Fact, FactContext, Observation, SourceType
from ntrp.memory.prefetch import (
    filter_prefetch_context,
    memory_prefetch_query,
    prefetch_memory_context,
)
from ntrp.services.chat import _retain_user_content, _time_gap_note
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from tests.helpers import MockCompletionClient, MockLLMClient, make_executor, make_test_executor, make_text_response

# --- Context block stripping ---


def test_retain_user_content():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "context", "content_type": "page_content", "content": "some page"},
                {"type": "text", "text": "hi"},
                {"type": "image", "media_type": "image/png", "data": "..."},
                {"type": "context", "content_type": "time_since_last_message", "content": "5 minutes"},
            ],
        },
        {"role": "assistant", "content": "hello"},
    ]
    result = _retain_user_content(messages)
    content = result[0]["content"]
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image"
    # original unchanged
    assert len(messages[0]["content"]) == 4


def test_retain_user_content_ignores_string_content():
    messages = [{"role": "user", "content": "just a normal message"}]
    result = _retain_user_content(messages)
    assert result[0]["content"] == "just a normal message"


def test_retain_user_content_ignores_non_user():
    messages = [{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}]
    result = _retain_user_content(messages)
    assert len(result[0]["content"]) == 1


def test_time_gap_note_short_gap():
    recent = datetime.now(UTC)
    assert _time_gap_note(recent) is None


def test_time_gap_note_long_gap():
    from datetime import timedelta

    old = datetime.now(UTC) - timedelta(hours=2)
    result = _time_gap_note(old)
    assert result is not None
    assert result["content_type"] == "time_since_last_message"
    assert "hour" in result["content"]


def _fact(fact_id: int, text: str) -> Fact:
    now = datetime.now(UTC)
    return Fact(
        id=fact_id,
        text=text,
        embedding=None,
        source_type=SourceType.EXPLICIT,
        source_ref=None,
        created_at=now,
        happened_at=None,
        last_accessed_at=now,
        access_count=0,
    )


def _observation(obs_id: int, summary: str, source_fact_ids: list[int]) -> Observation:
    now = datetime.now(UTC)
    return Observation(
        id=obs_id,
        summary=summary,
        embedding=None,
        evidence_count=len(source_fact_ids),
        source_fact_ids=source_fact_ids,
        history=[],
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        access_count=0,
    )


def test_memory_prefetch_query_is_conservative():
    assert memory_prefetch_query("") is None
    assert memory_prefetch_query("/memory") is None
    assert memory_prefetch_query("ok") is None
    assert memory_prefetch_query("check alice project") == "check alice project"


def test_filter_prefetch_context_removes_session_memory_duplicates():
    profile_fact = _fact(1, "User prefers concise replies")
    user_fact = _fact(2, "User works on ntrp")
    session_observation = _observation(10, "User often reviews backend architecture", [3])
    session_memory = SessionMemory(
        observations=[session_observation],
        profile_facts=[profile_fact],
        user_facts=[user_fact],
    )
    context = FactContext(
        facts=[profile_fact, user_fact, _fact(4, "Alice owns the launch doc")],
        observations=[session_observation, _observation(11, "Alice appears in project work", [4])],
        bundled_sources={
            10: [_fact(3, "Session source")],
            11: [_fact(4, "Alice owns the launch doc")],
        },
    )

    filtered = filter_prefetch_context(context, session_memory)

    assert [fact.id for fact in filtered.facts] == [4]
    assert [obs.id for obs in filtered.observations] == [11]
    assert list(filtered.bundled_sources) == [11]


def test_model_memory_context_keeps_facts_only_as_observation_evidence_when_possible():
    observation = _observation(11, "User wants consolidated memory in prompts", [4])
    bundled_fact = _fact(4, "User said raw facts are noisy")
    standalone_fact = _fact(5, "User mentioned a temporary UI bug")
    context = FactContext(
        facts=[standalone_fact],
        observations=[observation],
        bundled_sources={observation.id: [bundled_fact]},
    )

    shaped = model_memory_context(context)

    assert shaped.facts == []
    assert shaped.observations == [observation]
    assert shaped.bundled_sources == {observation.id: [bundled_fact]}


@pytest.mark.asyncio
async def test_prefetch_memory_context_can_be_prompt_context_without_session_snapshot():
    observation = _observation(11, "User is redesigning memory around contextual consolidated observations", [4])
    fact = _fact(4, "User rejected raw atomic prompt memory")

    class Memory:
        recorded = None

        async def inspect_recall(self, *, query: str, limit: int, query_time=None):
            assert query == "how should memory work now"
            assert limit == 3
            return FactContext(
                facts=[],
                observations=[observation],
                bundled_sources={observation.id: [fact]},
            )

        async def record_context_access(self, **kwargs):
            self.recorded = kwargs

    memory = Memory()

    rendered = await prefetch_memory_context(memory, "how should memory work now", source="chat_prefetch")

    assert rendered is not None
    assert "**Patterns**" in rendered
    assert "contextual consolidated observations" in rendered
    assert "raw atomic prompt memory" in rendered
    assert memory.recorded["injected_observation_ids"] == [observation.id]
    assert memory.recorded["bundled_fact_ids"] == [fact.id]


# --- Read connection sees committed writes ---


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "sessions.db")
    read_conn = await database.connect(tmp_path / "sessions.db", readonly=True)
    s = SessionStore(conn, read_conn)
    await s.init_schema()
    yield s
    await read_conn.close()
    await conn.close()


@pytest.mark.asyncio
async def test_read_conn_sees_committed_write(store: SessionStore):
    """Read connection should see data after write connection commits."""
    state = SessionState(session_id="vis", started_at=datetime.now(UTC))
    await store.save_session(state, [{"role": "user", "content": "test"}])

    # Read via read_conn
    loaded = await store.load_session("vis")
    assert loaded is not None
    assert loaded.messages[0]["content"] == "test"


@pytest.mark.asyncio
async def test_read_conn_sees_updated_sessions_list(store: SessionStore):
    """list_sessions uses read_conn and should see new sessions."""
    for i in range(3):
        state = SessionState(session_id=f"s-{i}", started_at=datetime.now(UTC))
        await store.save_session(state, [{"role": "user", "content": f"msg {i}"}])

    sessions = await store.list_sessions()
    assert len(sessions) == 3


# --- Agent with text + tool_calls in same response ---


class EchoInput(BaseModel):
    text: str = ""


async def echo(execution: ToolExecution, args: EchoInput) -> ToolResult:
    return ToolResult(content=f"echo: {args.text}", preview="echo")


ECHO_TOOL = tool(display_name="Echo", description="Echoes", input_model=EchoInput, execute=echo)


@pytest.mark.asyncio
async def test_agent_text_and_tool_calls():
    """Some models return both content and tool_calls. Agent should handle both."""
    from ntrp.agent import Choice, CompletionResponse, FunctionCall, Message, ToolCall, Usage

    mixed = CompletionResponse(
        choices=[
            Choice(
                message=Message(
                    role="assistant",
                    content="Let me check that for you.",
                    tool_calls=[
                        ToolCall(
                            id="c1", type="function", function=FunctionCall(name="echo", arguments='{"text":"hi"}')
                        ),
                    ],
                    reasoning_content=None,
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=Usage(),
        model="test-model",
    )

    client = MockCompletionClient([mixed, make_text_response("Here's the result")])
    executor = make_executor({"echo": ECHO_TOOL})
    agent = Agent(
        tools=executor.get_tools(),
        client=MockLLMClient(client),
        executor=make_test_executor(executor),
        model="test-model",
    )

    messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "Check something"}]
    result = await agent.run(messages)

    assert result.text == "Here's the result"
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert any("Let me check" in (m.get("content") or "") for m in assistant_msgs)


# --- Session with unicode and special chars ---


@pytest.mark.asyncio
async def test_save_unicode_content(store: SessionStore):
    state = SessionState(session_id="unicode", started_at=datetime.now(UTC))
    messages = [
        {"role": "user", "content": "日本語テスト 🎉 émojis and spëcial chars"},
        {"role": "assistant", "content": "Ответ на русском"},
    ]
    await store.save_session(state, messages)
    loaded = await store.load_session("unicode")
    assert "日本語" in loaded.messages[0]["content"]
    assert "🎉" in loaded.messages[0]["content"]
    assert "русском" in loaded.messages[1]["content"]


@pytest.mark.asyncio
async def test_save_message_with_newlines_and_quotes(store: SessionStore):
    state = SessionState(session_id="special", started_at=datetime.now(UTC))
    content = "He said \"hello\"\nand then\n\ttabbed in\nwith 'quotes' and \\backslashes"
    await store.save_session(state, [{"role": "user", "content": content}])
    loaded = await store.load_session("special")
    assert loaded.messages[0]["content"] == content


# --- Background registry: on_result callback ---


@pytest.mark.asyncio
async def test_registry_deliver_result_with_no_callback(tmp_path):
    """deliver_result with on_result=None should not crash (just warn)."""
    registry = BackgroundTaskRegistry(session_id=str(tmp_path))
    # No on_result set — should log warning but not crash
    await registry.deliver_result(
        task_id="t1",
        result="test result",
        label="test",
        status="completed",
        emit=None,
    )
    # Verify result file was still written
    result_file = Path(registry._write_result_file("t1_check", "check"))
    assert result_file.exists()


# --- Approval rejection when no UI ---


@pytest.mark.asyncio
async def test_approval_rejected_when_no_ui():
    """Tools requiring approval should be rejected when no UI is connected."""
    from ntrp.tools.core.context import Rejection

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),  # no emit, no approval_queue
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    execution = ToolExecution(tool_id="t1", tool_name="bash", ctx=ctx)

    result = await execution.request_approval("rm -rf something")
    assert isinstance(result, Rejection)
    assert "No UI" in result.feedback
