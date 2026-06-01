"""The `lens` tool — single tool, sub-actions (LENS_CONTRACTS §3.8, §10).

Offline: a fake LensService/projector standing in for the sibling-built service
(the tool depends only on the frozen interface). No store, no LLM, no network.

What these tests pin:
  - one tool, dispatched by `action` (not seven top-level tools);
  - each sub-action routes to the matching service call with the resolved scope;
  - missing-args land as tool errors, not exceptions;
  - the coverage advisory in `list` is surfaced as advisory prose only (§7);
  - the tool degrades cleanly when the lens service is absent (server boots with
    memory off — §10).
"""

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from ntrp.memory.lens.tool import LensInput, MEMORY_LENS_SERVICE, lens_action
from ntrp.memory.models import (
    Kind,
    LensDetailLevel,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
)

USER = Scope(kind=ScopeKind.USER)


@dataclass
class _Coverage:
    generic: bool = False
    ratio: float = 0.0
    suggestion: str = "narrow"


@dataclass
class _Page:
    markdown: str
    synthesized: bool = True


class FakeProjector:
    def __init__(self, page: _Page | None = None):
        self._page = page or _Page(markdown="# Lens\n- a fact. <!--claim:1-->")
        self.calls: list[dict] = []

    async def project(self, lens_id, *, detail=None, refresh=False):
        self.calls.append({"lens_id": lens_id, "detail": detail, "refresh": refresh})
        return self._page


def _lens(name="Marathon", criterion="marathon training", scope=USER) -> MemoryItem:
    return MemoryItem(
        id="lens-1",
        kind=Kind.LENS,
        content=name,
        scope=scope,
        provenance=Provenance.USER_AUTHORED,
        lens_name=name,
        lens_criterion=criterion,
        lens_kind="topic",
    )


class FakeLensService:
    def __init__(self):
        self.projector = FakeProjector()
        self.calls: list[tuple] = []

    async def create_lens(self, name, criterion, scope, *, lens_kind="topic"):
        self.calls.append(("create_lens", name, criterion, scope, lens_kind))
        return _lens(name, criterion, scope)

    async def list_lenses(self, scope):
        self.calls.append(("list_lenses", scope))
        return [(_lens(), _Coverage(generic=True, ratio=0.7, suggestion="split"))]

    async def edit_criterion(self, lens_id, new_criterion):
        self.calls.append(("edit_criterion", lens_id, new_criterion))
        return _lens(criterion=new_criterion)

    async def delete_lens(self, lens_id):
        self.calls.append(("delete_lens", lens_id))
        return True

    async def split_lens(self, lens_id, into):
        self.calls.append(("split_lens", lens_id, into))
        return [_lens(name=f"child-{i}") for i, _ in enumerate(into)]

    async def merge_lenses(self, lens_ids, name, criterion):
        self.calls.append(("merge_lenses", lens_ids, name, criterion))
        return _lens(name=name, criterion=criterion)


def _execution(svc, *, project=None):
    ctx = SimpleNamespace(
        services={MEMORY_LENS_SERVICE: svc} if svc is not None else {},
        project=project,
    )
    return SimpleNamespace(ctx=ctx)


@pytest.mark.asyncio
async def test_define_routes_to_create_lens():
    svc = FakeLensService()
    res = await lens_action(
        _execution(svc),
        LensInput(action="define", name="Marathon", criterion="marathon training"),
    )
    assert not res.is_error
    assert svc.calls[0][0] == "create_lens"
    assert svc.calls[0][3] == USER  # USER scope outside a project
    assert res.data["lens_id"] == "lens-1"


@pytest.mark.asyncio
async def test_define_in_project_scope():
    svc = FakeLensService()
    project = SimpleNamespace(project_id="proj-9")
    await lens_action(
        _execution(svc, project=project),
        LensInput(action="define", name="X", criterion="y"),
    )
    scope = svc.calls[0][3]
    assert scope.kind is ScopeKind.PROJECT and scope.key == "proj-9"


@pytest.mark.asyncio
async def test_show_routes_to_projector_and_returns_markdown():
    svc = FakeLensService()
    res = await lens_action(
        _execution(svc), LensInput(action="show", lens_id="lens-1", detail="dossier")
    )
    assert not res.is_error
    assert "a fact" in res.content
    assert svc.projector.calls[0]["lens_id"] == "lens-1"
    assert svc.projector.calls[0]["detail"] is LensDetailLevel.DOSSIER


@pytest.mark.asyncio
async def test_show_raw_fallback_preview():
    svc = FakeLensService()
    svc.projector = FakeProjector(_Page(markdown="- raw <!--claim:1-->", synthesized=False))
    res = await lens_action(_execution(svc), LensInput(action="show", lens_id="lens-1"))
    assert res.preview == "Lens page (raw)"


@pytest.mark.asyncio
async def test_edit_routes_to_edit_criterion():
    svc = FakeLensService()
    res = await lens_action(
        _execution(svc), LensInput(action="edit", lens_id="lens-1", criterion="new crit")
    )
    assert not res.is_error
    assert svc.calls[0] == ("edit_criterion", "lens-1", "new crit")


@pytest.mark.asyncio
async def test_delete_routes_to_delete_lens():
    svc = FakeLensService()
    res = await lens_action(_execution(svc), LensInput(action="delete", lens_id="lens-1"))
    assert not res.is_error
    assert svc.calls[0] == ("delete_lens", "lens-1")
    assert "claims" in res.content.lower()  # delete-leaves-claims promise surfaced


@pytest.mark.asyncio
async def test_split_routes_with_paired_criteria():
    svc = FakeLensService()
    res = await lens_action(
        _execution(svc),
        LensInput(action="split", lens_id="lens-1", into=["crit a", "crit b"]),
    )
    assert not res.is_error
    name, lens_id, into = svc.calls[0]
    assert name == "split_lens" and lens_id == "lens-1"
    assert into == [("crit a", "crit a"), ("crit b", "crit b")]
    assert len(res.data["lens_ids"]) == 2


@pytest.mark.asyncio
async def test_merge_routes_to_merge_lenses():
    svc = FakeLensService()
    res = await lens_action(
        _execution(svc),
        LensInput(action="merge", lens_ids=["a", "b"], name="Union", criterion="both"),
    )
    assert not res.is_error
    assert svc.calls[0] == ("merge_lenses", ["a", "b"], "Union", "both")


@pytest.mark.asyncio
async def test_list_surfaces_coverage_advisory_as_prose():
    svc = FakeLensService()
    res = await lens_action(_execution(svc), LensInput(action="list"))
    assert not res.is_error
    # Advisory only: a prose note, never a gate or a mutation.
    assert "generic" in res.content and "split" in res.content and "70%" in res.content


@pytest.mark.asyncio
async def test_missing_args_are_tool_errors_not_exceptions():
    svc = FakeLensService()
    for args in (
        LensInput(action="define", name="x"),  # missing criterion
        LensInput(action="show"),  # missing lens_id
        LensInput(action="edit", lens_id="l"),  # missing criterion
        LensInput(action="delete"),  # missing lens_id
        LensInput(action="split", lens_id="l"),  # missing into
        LensInput(action="merge", lens_ids=["a"]),  # missing name/criterion
    ):
        res = await lens_action(_execution(svc), args)
        assert res.is_error
    assert svc.calls == []  # no service call made on a bad request


@pytest.mark.asyncio
async def test_unknown_action_errors():
    res = await lens_action(_execution(FakeLensService()), LensInput(action="frobnicate"))
    assert res.is_error and "Unknown action" in res.content


@pytest.mark.asyncio
async def test_missing_service_degrades_cleanly():
    res = await lens_action(_execution(None), LensInput(action="list"))
    assert res.is_error and "not available" in res.content.lower()
