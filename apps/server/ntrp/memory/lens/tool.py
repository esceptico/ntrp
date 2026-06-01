"""The single `lens` tool — define/show/edit/delete/split/merge/list (§3.8).

One tool with sub-actions, NOT seven top-level tools (the surface stays small;
agent specializations are not tools). Everyday recall stays the `recall` tool,
which transparently uses `lens_hint`; this tool is the deliberate, user-invoked
surface for materialized views over the knowledge graph.

It delegates to the `LensRegistry` (registry CRUD over the `lenses` table) + the
`LensProjector` (read-only projected page), surfaced together behind one service
slot (`MEMORY_LENS_SERVICE`). The slot is wired by the knowledge runtime only
inside the `memory_ready` branch, so the server boots unchanged with memory off.

The absolute ban (§0) does not arise here: this tool makes no membership
decisions. `define`/`split`/`merge` create registry rows (zero claims touched) and
the membership projection collects matching claims on demand; `show` reads the
projected page; the coverage advisory is a pure COUNT ratio, never a gate.
"""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ntrp.logging import get_logger
from ntrp.memory.models import (
    LensDetailLevel,
    LensRow,
    Scope,
    ScopeKind,
)
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope

_logger = get_logger(__name__)

MEMORY_LENS_SERVICE = "memory_lens"


# --- frozen dependency interfaces (built by sibling components) ----------
# The tool depends only on these shapes, never on the implementations. The
# concrete `LensService`/`LensProjector` live in ntrp/memory/pipeline/ (§8) and
# are bound to MEMORY_LENS_SERVICE by the knowledge runtime in the integration
# phase. Re-declared here as Protocols so this slice neither imports nor forks
# the pipeline package.


@runtime_checkable
class ProjectorProtocol(Protocol):
    async def project(
        self, lens_id: str, *, detail: LensDetailLevel | None = ..., refresh: bool = ...
    ): ...


@runtime_checkable
class LensServiceProtocol(Protocol):
    projector: ProjectorProtocol

    async def create_lens(self, name: str, criterion: str, scope: Scope) -> LensRow: ...

    async def list_lenses(self, scope: Scope) -> list[tuple[LensRow, object]]: ...

    async def edit_criterion(self, lens_id: str, new_criterion: str) -> LensRow: ...

    async def delete_lens(self, lens_id: str) -> bool: ...

    async def split_lens(
        self, lens_id: str, into: list[tuple[str, str]]
    ) -> list[LensRow]: ...

    async def merge_lenses(
        self, lens_ids: list[str], name: str, criterion: str
    ) -> LensRow: ...


# --- tool input ----------------------------------------------------------


class LensInput(BaseModel):
    action: str = Field(
        description=(
            "What to do: 'define' (create a lens from a name + criterion), 'show' "
            "(render a lens's markdown page), 'edit' (rewrite a lens's criterion), "
            "'delete' (archive the view; claims are never deleted), 'split' (break "
            "a too-broad lens into narrower ones), 'merge' (union several lenses), "
            "or 'list' (every lens in scope with its coverage advisory)."
        ),
    )
    name: str | None = Field(
        default=None,
        description="Lens name. Required for 'define'/'merge'; the title shown on the page.",
    )
    criterion: str | None = Field(
        default=None,
        description=(
            "Natural-language membership criterion — the canonical truth of the "
            "lens (e.g. 'anything about the user's marathon training'). Required "
            "for 'define'/'edit'/'merge'; membership is judged against it."
        ),
    )
    lens_id: str | None = Field(
        default=None,
        description="Target lens id. Required for 'show'/'edit'/'delete'/'split'.",
    )
    detail: str | None = Field(
        default=None,
        description=(
            "For 'show': zoom level — 'gist' (one paragraph), 'structured' (the "
            "editable bullet list, default), or 'dossier' (structured + evidence)."
        ),
    )
    into: list[str] | None = Field(
        default=None,
        description=(
            "For 'split': the child criteria to split into (one new lens per "
            "criterion); the child name is derived from the parent."
        ),
    )
    lens_ids: list[str] | None = Field(
        default=None,
        description="For 'merge': the ids of the lenses to union into one.",
    )


def _resolve_scope(execution: ToolExecution) -> Scope:
    """Scope from the active project, else USER. Structural, never LLM-inferred
    (mirrors tools/memory.py:_resolve_scope)."""
    project = execution.ctx.project
    if project is not None and project.project_id:
        return Scope(kind=ScopeKind.PROJECT, key=str(project.project_id))
    return Scope(kind=ScopeKind.USER)


def _detail(value: str | None) -> LensDetailLevel | None:
    if value is None:
        return None
    try:
        return LensDetailLevel(value)
    except ValueError:
        return None


def _coverage_note(advisory: object) -> str:
    """One-line advisory string from a CoverageAdvisory-shaped object (§7).

    Advisory only: it never gates or mutates anything. Tolerant of a missing/
    differently-shaped object (the advisory is built by a sibling component)."""
    generic = getattr(advisory, "generic", False)
    if not generic:
        return ""
    ratio = getattr(advisory, "ratio", 0.0)
    suggestion = getattr(advisory, "suggestion", "narrow")
    return f"  [generic: covers {ratio:.0%} of scope — consider to {suggestion}]"


async def _do_define(svc: LensServiceProtocol, args: LensInput, scope: Scope) -> ToolResult:
    if not args.name or not args.criterion:
        return ToolResult.error("define requires both 'name' and 'criterion'.")
    lens = await svc.create_lens(args.name, args.criterion, scope)
    return ToolResult(
        content=f"Created lens '{lens.name}' ({lens.id}). It collects matching claims on demand.",
        preview=f"Lens '{lens.name}'",
        data={"lens_id": lens.id},
    )


async def _do_show(svc: LensServiceProtocol, args: LensInput) -> ToolResult:
    if not args.lens_id:
        return ToolResult.error("show requires 'lens_id'.")
    page = await svc.projector.project(args.lens_id, detail=_detail(args.detail))
    markdown = getattr(page, "markdown", "") or ""
    if not markdown:
        return ToolResult(content="Lens page is empty.", preview="Empty lens")
    synthesized = getattr(page, "synthesized", True)
    preview = "Lens page" if synthesized else "Lens page (raw)"
    return ToolResult(content=markdown, preview=preview, data={"lens_id": args.lens_id})


async def _do_edit(svc: LensServiceProtocol, args: LensInput) -> ToolResult:
    if not args.lens_id or not args.criterion:
        return ToolResult.error("edit requires 'lens_id' and the new 'criterion'.")
    lens = await svc.edit_criterion(args.lens_id, args.criterion)
    return ToolResult(
        content=f"Rewrote criterion of '{lens.name}'. Membership re-derives at next view.",
        preview="Criterion updated",
        data={"lens_id": lens.id},
    )


async def _do_delete(svc: LensServiceProtocol, args: LensInput) -> ToolResult:
    if not args.lens_id:
        return ToolResult.error("delete requires 'lens_id'.")
    ok = await svc.delete_lens(args.lens_id)
    if not ok:
        return ToolResult(content="Lens not found or already archived.", preview="No change")
    return ToolResult(
        content="Archived the lens. Its claims and memberships are untouched.",
        preview="Lens archived",
    )


async def _do_split(svc: LensServiceProtocol, args: LensInput) -> ToolResult:
    if not args.lens_id or not args.into:
        return ToolResult.error("split requires 'lens_id' and 'into' (child criteria).")
    children = await svc.split_lens(args.lens_id, [(c, c) for c in args.into])
    ids = [c.id for c in children]
    return ToolResult(
        content=f"Split into {len(children)} lens(es): {', '.join(ids)}.",
        preview=f"Split into {len(children)}",
        data={"lens_ids": ids},
    )


async def _do_merge(svc: LensServiceProtocol, args: LensInput) -> ToolResult:
    if not args.lens_ids or not args.name or not args.criterion:
        return ToolResult.error("merge requires 'lens_ids', 'name', and 'criterion'.")
    lens = await svc.merge_lenses(args.lens_ids, args.name, args.criterion)
    return ToolResult(
        content=f"Merged into '{lens.name}' ({lens.id}); members re-derived.",
        preview=f"Merged into '{lens.name}'",
        data={"lens_id": lens.id},
    )


async def _do_list(svc: LensServiceProtocol, scope: Scope) -> ToolResult:
    rows = await svc.list_lenses(scope)
    if not rows:
        return ToolResult(content="No lenses in this scope.", preview="No lenses")
    lines = []
    for lens, advisory in rows:
        lines.append(f"- {lens.name} ({lens.id}): {lens.criterion}{_coverage_note(advisory)}")
    return ToolResult(content="\n".join(lines), preview=f"{len(rows)} lens(es)")


_ACTIONS = {
    "define": lambda svc, args, scope: _do_define(svc, args, scope),
    "show": lambda svc, args, scope: _do_show(svc, args),
    "edit": lambda svc, args, scope: _do_edit(svc, args),
    "delete": lambda svc, args, scope: _do_delete(svc, args),
    "split": lambda svc, args, scope: _do_split(svc, args),
    "merge": lambda svc, args, scope: _do_merge(svc, args),
    "list": lambda svc, args, scope: _do_list(svc, scope),
}


async def lens_action(execution: ToolExecution, args: LensInput) -> ToolResult:
    svc = execution.ctx.services.get(MEMORY_LENS_SERVICE)
    if not isinstance(svc, LensServiceProtocol):
        return ToolResult(
            content="Memory lenses are not available.",
            preview="Lenses unavailable",
            is_error=True,
        )

    handler = _ACTIONS.get(args.action)
    if handler is None:
        return ToolResult.error(
            f"Unknown action '{args.action}'. "
            f"Valid: {', '.join(sorted(_ACTIONS))}."
        )

    return await handler(svc, args, _resolve_scope(execution))


lens_tool = tool(
    display_name="Lens",
    description=(
        "Manage materialized views over long-term memory ('lenses'): a named "
        "natural-language criterion plus an editable markdown page that "
        "auto-collects matching facts. Use 'define' to create one, 'show' to read "
        "its page, 'edit' to refine its criterion, 'list' to see all in scope (with "
        "coverage advisories), and 'split'/'merge' to reshape them. Everyday recall "
        "does not need this — use it to curate durable, topic-shaped views."
    ),
    input_model=LensInput,
    policy=ToolPolicy(
        action=ToolAction.WRITE,
        scope=ToolScope.INTERNAL,
        permissions=frozenset({MEMORY_LENS_SERVICE}),
    ),
    execute=lens_action,
)
