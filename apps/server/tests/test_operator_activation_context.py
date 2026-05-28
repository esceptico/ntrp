from datetime import UTC, datetime

import pytest

from ntrp.context.models import SessionState
from ntrp.core.factory import AgentConfig
from ntrp.memory.activation import MemoryActivationBundle
from ntrp.operator import runner
from ntrp.operator.runner import OperatorDeps, RunRequest


class _Executor:
    def get_tools(self, read_only: bool = False):
        return []


class _AccessEvents:
    def __init__(self) -> None:
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


class _MemoryService:
    def __init__(self) -> None:
        self.access_events = _AccessEvents()


class _FakeMemoryRetrieval:
    def __init__(self, bundle: MemoryActivationBundle):
        self.bundle = bundle
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        return self.bundle


@pytest.mark.asyncio
async def test_operator_prepare_passes_run_and_session_ids_to_retrieval(monkeypatch):
    created_agents = []
    system_kwargs = []
    retrieval = _FakeMemoryRetrieval(
        MemoryActivationBundle(
            query="audit memory",
            scope="source:source-1",
            kinds=None,
            used_chars=18,
            candidates=[],
            prompt_context="<memory>ctx</memory>",
            usage_event_id=99,
        )
    )
    memory_service = _MemoryService()

    def fake_create_agent(**kwargs):
        created_agents.append(kwargs)
        return object()

    monkeypatch.setattr(runner, "create_agent", fake_create_agent)

    def fake_build_system_prompt(**kwargs):
        system_kwargs.append(kwargs)
        return "system"

    monkeypatch.setattr(runner, "build_system_prompt", fake_build_system_prompt)
    monkeypatch.setattr(runner, "load_directives", lambda: None)

    deps = OperatorDeps(
        executor=_Executor(),
        memory=None,
        memory_service=memory_service,
        config=AgentConfig(model="gpt-5.2", research_model=None, max_depth=1, deferred_tools=False),
        source_details={},
        create_session=lambda: SessionState(session_id="operator-session-1", started_at=datetime.now(UTC)),
        notifiers=[],
        memory_retrieval=retrieval,
    )

    _, _, run_id, session_id = await runner._prepare(
        deps,
        RunRequest(prompt="audit memory", writable=False, source_id="source-1", automation_id="automation-1"),
    )

    assert session_id == "operator-session-1"
    assert run_id
    assert retrieval.requests
    assert retrieval.requests[0].task == "operator_prompt"
    assert retrieval.requests[0].task_id == "automation-1"
    assert retrieval.requests[0].session_id == "operator-session-1"
    assert retrieval.requests[0].run_id == run_id
    assert created_agents[0]["session_state"].session_id == "operator-session-1"
    assert created_agents[0]["run_id"] == run_id
    assert system_kwargs[0]["memory_context"] == "<memory>ctx</memory>"
    assert memory_service.access_events.calls == []
