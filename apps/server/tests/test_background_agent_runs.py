import asyncio
from datetime import UTC, datetime

import pytest

import ntrp.tools.background as background_module
from ntrp.context.models import SessionState
from ntrp.core.spawner import SpawnResult
from ntrp.memory.activation import MemoryActivationBundle
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry


@pytest.mark.asyncio
async def test_background_registry_records_started_activity_and_completed():
    calls = []

    async def record(**kwargs):
        calls.append(kwargs)

    results = {}

    async def read_result(task_id):
        return results.get(task_id)

    registry = BackgroundTaskRegistry(session_id="sess-1", record_event=record, read_result=read_result)
    task = asyncio.create_task(asyncio.sleep(0))
    await registry.record_started(task_id="bg-1", command="research", parent_run_id="run-1")
    registry.register("bg-1", task, command="research")
    await registry.record_activity("bg-1", "read files")
    await registry.deliver_result(
        task_id="bg-1",
        result="done",
        label="research",
        status="completed",
        emit=None,
    )

    assert [c["status"] for c in calls] == ["started", "activity", "completed"]
    assert calls[0]["session_id"] == "sess-1"
    assert calls[0]["parent_run_id"] == "run-1"
    assert calls[-1]["terminal"] is True
    assert calls[-1]["result_text"] == "done"

    results["bg-1"] = "done"
    assert await registry.read_background_result("bg-1") == "done"


@pytest.mark.asyncio
async def test_background_registry_injects_hidden_meta_completion_with_result():
    injected = []

    async def on_result(messages):
        injected.extend(messages)

    registry = BackgroundTaskRegistry(session_id="sess-1", on_result=on_result)

    await registry.deliver_result(
        task_id="bg-1",
        result="email summary",
        label="fetch email",
        status="completed",
        emit=None,
    )

    assert injected == [
        {
            "role": "user",
            "content": (
                '<background_agent_result task_id="bg-1" status="completed">\n'
                "This is a hidden completion event. The user cannot see this message.\n"
                "Write a visible assistant response now. Summarize the result directly for the user.\n"
                "If the result contains sources, IDs, links, or evidence, include the relevant ones inline.\n"
                "Do not say the sources/result are above, hidden, attached, in a file, or in the bg result.\n\n"
                "<result>\nemail summary\n</result>\n"
                "</background_agent_result>"
            ),
            "is_meta": True,
            "client_id": "bg:bg-1:completed",
        }
    ]


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


def _tool_context(*, spawn_fn=None, memory=None, memory_retrieval=None, skill_registry=None) -> ToolContext:
    services = {"memory": memory, "skill_registry": skill_registry}
    if memory_retrieval is not None:
        services["memory_retrieval"] = memory_retrieval
    ctx = ToolContext(
        session_state=SessionState(session_id="sess-bg", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-bg", current_depth=0, max_depth=3),
        io=IOBridge(),
        services=services,
        background_tasks=BackgroundTaskRegistry(session_id="sess-bg"),
    )
    ctx.spawn_fn = spawn_fn
    return ctx


@pytest.mark.asyncio
async def test_background_tool_passes_runtime_context_to_memory_retrieval():
    captured = {}
    memory = _MemoryService()
    retrieval = _FakeMemoryRetrieval(
        MemoryActivationBundle(
            query="audit background memory loop",
            scope=None,
            kinds=None,
            used_chars=27,
            candidates=[],
            prompt_context="<memory>background memory</memory>",
        )
    )

    async def spawn_fn(ctx, task, **kwargs):
        captured["spawn"] = kwargs
        captured["task"] = task
        return SpawnResult(text="background done")

    execution = ToolExecution(
        tool_id="background-1",
        tool_name="background",
        ctx=_tool_context(spawn_fn=spawn_fn, memory=memory, memory_retrieval=retrieval),
    )

    result = await background_module.background(
        execution,
        background_module.BackgroundInput(task="audit background memory loop"),
    )

    assert result.content == "background done"
    request = retrieval.requests[0]
    assert request.task == "background_prompt"
    assert request.task_id == "background-1"
    assert request.session_id == "sess-bg"
    assert request.run_id == "run-bg"
    assert request.surface == "prompt"
    system_prompt = captured["spawn"]["system_prompt"]
    assert "<memory>background memory</memory>" in system_prompt
    assert "<activated_skills>" not in system_prompt
    assert memory.access_events.calls == []
