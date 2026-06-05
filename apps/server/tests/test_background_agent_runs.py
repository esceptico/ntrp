import asyncio

import pytest

from ntrp.tools.core.context import BackgroundTaskRegistry


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
    await registry.record_started(
        task_id="bg-1",
        command="research",
        parent_run_id="run-1",
        parent_tool_call_id="call-background",
        agent_type="background_research",
        wait=False,
    )
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
    assert calls[0]["parent_tool_call_id"] == "call-background"
    assert calls[0]["agent_type"] == "background_research"
    assert calls[0]["wait"] is False
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
