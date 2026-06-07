from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from ntrp.orchestra.engine import Orchestra
from ntrp.orchestra.schema import coerce, extract_json


class _Schema(BaseModel):
    value: int


def _ctx_with(responses: list[str]):
    calls = {"i": 0}

    async def spawn_fn(ctx, *, task, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        text = responses[i] if i < len(responses) else responses[-1]
        return SimpleNamespace(text=text)

    return SimpleNamespace(spawn_fn=spawn_fn), calls


def test_extract_json_plain():
    assert extract_json('{"value": 1}') == '{"value": 1}'


def test_coerce_fenced():
    assert coerce('```json\n{"value": 5}\n```', _Schema).value == 5


def test_coerce_prose_wrapped():
    assert coerce('Here you go: {"value": 7} done', _Schema).value == 7


def test_coerce_invalid_raises():
    with pytest.raises(ValidationError):
        coerce("not json at all", _Schema)


def test_coerce_trailing_prose():
    assert coerce('{"value": 1}\n\nLet me know if you need anything else.', _Schema).value == 1


def test_coerce_two_objects_takes_first():
    assert coerce('here {"value": 1} and also {"value": 2}', _Schema).value == 1


def test_coerce_fenced_with_trailing():
    assert coerce('```json\n{"value": 8}\n```\nthanks!', _Schema).value == 8


async def test_agent_returns_text_without_schema():
    ctx, _ = _ctx_with(["hello world"])
    o = Orchestra.for_ctx(ctx)
    assert await o.agent("say hi") == "hello world"


async def test_agent_coerces_schema():
    ctx, _ = _ctx_with(['{"value": 42}'])
    o = Orchestra.for_ctx(ctx)
    result = await o.agent("give me value", schema=_Schema)
    assert result.value == 42


async def test_agent_repairs_invalid_json_once():
    ctx, calls = _ctx_with(["garbage", '{"value": 9}'])
    o = Orchestra.for_ctx(ctx)
    result = await o.agent("give me value", schema=_Schema)
    assert result.value == 9
    assert calls["i"] == 2


async def test_agent_raises_value_error_on_double_failure():
    ctx, _ = _ctx_with(["garbage", "still garbage"])
    o = Orchestra.for_ctx(ctx)
    with pytest.raises(ValueError):
        await o.agent("give me value", schema=_Schema)


async def test_parallel_swallows_double_failure_to_none():
    ctx, _ = _ctx_with(["garbage", "still garbage"])
    o = Orchestra.for_ctx(ctx)
    results = await o.parallel([(lambda: o.agent("x", schema=_Schema))])
    assert results == [None]


async def test_parallel_preserves_order_and_isolates_failures():
    async def ok(v):
        return v

    async def boom():
        raise RuntimeError("nope")

    ctx, _ = _ctx_with(["x"])
    o = Orchestra.for_ctx(ctx)
    results = await o.parallel([(lambda: ok(1)), (lambda: boom()), (lambda: ok(3))])
    assert results == [1, None, 3]


async def test_pipeline_runs_all_stages_per_item():
    ctx, _ = _ctx_with(["x"])
    o = Orchestra.for_ctx(ctx)

    async def stage1(prev, item, i):
        return item * 2

    async def stage2(prev, item, i):
        return prev + 1

    results = await o.pipeline([1, 2, 3], stage1, stage2)
    assert results == [3, 5, 7]


async def test_pipeline_drops_item_on_none_stage():
    ctx, _ = _ctx_with(["x"])
    o = Orchestra.for_ctx(ctx)

    async def stage1(prev, item, i):
        return None if item == 2 else item

    async def stage2(prev, item, i):
        return prev * 10

    results = await o.pipeline([1, 2, 3], stage1, stage2)
    assert results == [10, None, 30]


async def test_pipeline_isolates_stage_exceptions():
    ctx, _ = _ctx_with(["x"])
    o = Orchestra.for_ctx(ctx)

    async def stage1(prev, item, i):
        if item == 2:
            raise RuntimeError("boom")
        return item

    results = await o.pipeline([1, 2, 3], stage1)
    assert results == [1, None, 3]


async def test_parallel_spawns_get_unique_lifecycle_ids():
    seen = []

    async def spawn_fn(ctx, *, task, lifecycle_id=None, **kwargs):
        seen.append(lifecycle_id)
        return SimpleNamespace(text="ok")

    ctx = SimpleNamespace(spawn_fn=spawn_fn)
    o = Orchestra.for_ctx(ctx, parent_id="tool-1", workflow_id="wf-1")
    await o.parallel([(lambda: o.agent("a")), (lambda: o.agent("b")), (lambda: o.agent("c"))])
    assert len(seen) == 3
    assert len(set(seen)) == 3
    assert all(s and s.startswith("tool-1:") for s in seen)


async def test_workflow_agents_exclude_spawn_tools():
    captured = {}

    async def spawn_fn(ctx, *, task, exclude_tools=None, **kwargs):
        captured["exclude"] = exclude_tools
        return SimpleNamespace(text="ok")

    ctx = SimpleNamespace(spawn_fn=spawn_fn)
    o = Orchestra.for_ctx(ctx, parent_id="t", workflow_id="w")
    await o.agent("do thing")
    assert captured["exclude"] is not None
    assert {"workflow", "research", "background"} <= set(captured["exclude"])
