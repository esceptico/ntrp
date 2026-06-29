import asyncio

from pydantic import BaseModel, ConfigDict

from ntrp.agent import ToolResult
from ntrp.tools.core.base import RESERVED_ARG_KEYS, TITLE_ARG, Tool
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope


class _StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # mirrors EmptyInput / todos
    path: str


class _StrictTool(Tool):
    description = "reads a path"
    policy = ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL)
    input_model = _StrictIn

    async def execute(self, execution, **kwargs):  # type: ignore[override]
        return ToolResult(content=f"ok:{kwargs['path']}", preview="ok")


def test_title_is_injected_into_every_tool_schema_as_optional():
    params = _StrictTool().to_dict("readish")["function"]["parameters"]
    assert TITLE_ARG in params["properties"]
    assert TITLE_ARG not in params["required"]  # optional — never forces the model
    # Injected first so it streams before the real args.
    assert next(iter(params["properties"])) == TITLE_ARG


def test_title_is_stripped_before_execute_even_for_forbid_models():
    reg = ToolRegistry()
    reg.register("readish", _StrictTool(), source="_system")
    # The model emits a title alongside the real arg; an extra="forbid" input
    # model would raise if `title` reached it — the registry must strip it.
    res = asyncio.run(reg.execute("readish", None, {"title": "Reading the doc", "path": "a.py"}))
    assert not res.is_error
    assert res.content == "ok:a.py"


def test_reserved_keys_cover_title():
    assert TITLE_ARG in RESERVED_ARG_KEYS
