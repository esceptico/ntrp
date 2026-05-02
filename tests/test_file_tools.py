from datetime import UTC, datetime

import pytest

from ntrp.context.models import SessionState
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.deferred import is_deferred_tool
from ntrp.tools.executor import ToolExecutor
from ntrp.tools.files import (
    edit_file_tool,
    find_files_tool,
    list_files_tool,
    search_text_tool,
    write_file_tool,
)


def _make_execution(tool_name: str) -> ToolExecution:
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    return ToolExecution(tool_id="t1", tool_name=tool_name, ctx=ctx)


@pytest.mark.asyncio
async def test_list_files_returns_directory_entries(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")

    result = await list_files_tool.execute(_make_execution("list_files"), path=str(tmp_path))

    assert not result.is_error
    assert "README.md" in result.content
    assert "src/" in result.content
    assert result.data["total"] == 2


@pytest.mark.asyncio
async def test_find_files_matches_glob_recursively(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "app.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")

    result = await find_files_tool.execute(_make_execution("find_files"), path=str(tmp_path), pattern="*.py")

    assert not result.is_error
    assert "pkg/app.py" in result.content
    assert result.data["matches"] == [
        {"path": str(tmp_path / "pkg" / "app.py"), "relative_path": "pkg/app.py", "size": "11B"}
    ]


@pytest.mark.asyncio
async def test_search_text_returns_line_matches(tmp_path):
    (tmp_path / "one.txt").write_text("alpha\nneedle here\n", encoding="utf-8")
    (tmp_path / "two.txt").write_text("nothing\n", encoding="utf-8")

    result = await search_text_tool.execute(_make_execution("search_text"), path=str(tmp_path), query="needle")

    assert not result.is_error
    assert "one.txt:2:" in result.content
    assert result.data["matches"][0]["text"] == "needle here"


@pytest.mark.asyncio
async def test_write_file_writes_exact_content(tmp_path):
    target = tmp_path / "new.txt"

    result = await write_file_tool.execute(_make_execution("write_file"), path=str(target), content="a\nb\n")

    assert not result.is_error
    assert target.read_text(encoding="utf-8") == "a\nb\n"
    assert result.data == {"path": str(target), "lines": 3}


@pytest.mark.asyncio
async def test_edit_file_replaces_one_exact_block(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("hello old world\n", encoding="utf-8")

    result = await edit_file_tool.execute(
        _make_execution("edit_file"),
        path=str(target),
        old_text="old",
        new_text="new",
    )

    assert not result.is_error
    assert target.read_text(encoding="utf-8") == "hello new world\n"


@pytest.mark.asyncio
async def test_edit_file_rejects_ambiguous_block(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("same\nsame\n", encoding="utf-8")

    result = await edit_file_tool.execute(
        _make_execution("edit_file"),
        path=str(target),
        old_text="same",
        new_text="different",
    )

    assert result.is_error
    assert "matched 2 times" in result.content
    assert target.read_text(encoding="utf-8") == "same\nsame\n"


def test_file_tools_are_registered_as_core_tools():
    executor = ToolExecutor()

    names = set(executor.registry.tools)

    assert {"read_file", "list_files", "find_files", "search_text", "write_file", "edit_file"}.issubset(names)
    assert not is_deferred_tool("read_file", executor.registry)
    assert not is_deferred_tool("list_files", executor.registry)
    assert not is_deferred_tool("find_files", executor.registry)
    assert not is_deferred_tool("search_text", executor.registry)
    assert is_deferred_tool("write_file", executor.registry)
    assert is_deferred_tool("edit_file", executor.registry)


@pytest.mark.asyncio
async def test_write_file_requires_approval_through_registry(tmp_path):
    target = tmp_path / "new.txt"
    registry = ToolRegistry()
    registry.register("write_file", write_file_tool)
    execution = _make_execution("write_file")

    result = await registry.execute("write_file", execution, {"path": str(target), "content": "hello"})

    assert result.preview == "Rejected"
    assert not target.exists()
