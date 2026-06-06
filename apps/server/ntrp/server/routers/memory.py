"""Memory UI router (Stage-5) — read + structured write-back over the frozen store.

Thin HTTP surface over `MemoryStore` (claim reads + the `lenses` registry),
`LensRegistry`/`LensProjector` (lens lifecycle + projected page), `LensWriteBack`
(anchored page edits), and `MemoryPipeline.retrieve` (ranked egress). Memory is
claims-only; lenses are a separate registry of views (never graph nodes). The
graph is claims + claim↔claim edges only.

Wiring: `require_knowledge_runtime` → `KnowledgeRuntime`. Reads use
`knowledge.memory` (the store); lens/page/writeback/retrieve use
`knowledge.memory_retrieval` (the pipeline, exposing `.lens_registry`,
`.lens_projector`, `.lens_writeback`, `.retrieve`). Every route guards
`knowledge.memory_ready` → 503 when the pipeline is not up.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ntrp.memory.models import (
    EdgeRole,
    LensDetailLevel,
    LensRenderMode,
    LensRow,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    SourceRef,
    Status,
)
from ntrp.memory.pipeline.write import WriteRequest, WriteSeam
from ntrp.memory.pipeline.types import (
    CoverageAdvisory,
    PageEditKind,
    PageEditOp,
    ProjectedGroup,
    ProjectedPage,
    RankedItem,
    RenderedClaim,
    Retrieval,
    RetrievedContext,
    WriteBackResult,
)
from ntrp.server.deps import require_knowledge_runtime
from ntrp.server.runtime.knowledge import KnowledgeRuntime
from ntrp.server.schemas import (
    CreateLensBody,
    DraftLensBody,
    EditCriterionBody,
    MergeLensBody,
    RememberBody,
    SetLensRenderModeBody,
    SplitLensBody,
    WriteBackOpsBody,
)

router = APIRouter(prefix="/admin/memory", tags=["memory"])

_MAX_GRAPH_DEPTH = 5


# --- shared helpers --------------------------------------------------


def _knowledge(knowledge: KnowledgeRuntime = Depends(require_knowledge_runtime)) -> KnowledgeRuntime:
    if not knowledge.memory_ready:
        raise HTTPException(status_code=503, detail="memory pipeline not ready")
    return knowledge


def _scope(scope_kind: str, scope_key: str | None) -> Scope:
    try:
        return Scope(kind=ScopeKind(scope_kind), key=scope_key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _scope_or_all(scope_kind: str, scope_key: str | None) -> Scope | None:
    """`all` / empty → None (no scope filter): memory is ONE connected store the user
    browses unified; scope is an optional filter, not a wall. Isolation governs what
    the agent recalls, not what the human inspects."""
    if not scope_kind or scope_kind == "all":
        return None
    return _scope(scope_kind, scope_key)


def _scope_json(scope: Scope) -> dict:
    return {"kind": scope.kind.value, "key": scope.key}


def _pin_write_request(fact: str, project_id: str | None) -> WriteRequest:
    """A USER_AUTHORED claim from a manual pin — same shape as the remember()
    tool (bypass_admit, project scope when available, else USER)."""
    scope = (
        Scope(kind=ScopeKind.PROJECT, key=project_id)
        if project_id
        else Scope(kind=ScopeKind.USER)
    )
    return WriteRequest(
        content=fact,
        scope=scope,
        provenance=Provenance.USER_AUTHORED,
        source_refs=[SourceRef(kind="desktop_pin", ref="agent_result")],
        valid_from=None,
        bypass_admit=True,
    )


def item_json(m: MemoryItem) -> dict:
    return {
        "id": m.id,
        "content": m.content,
        "canonical_subject": m.canonical_subject,
        "scope": _scope_json(m.scope),
        "provenance": m.provenance.value,
        "status": m.status.value,
        "valid_from": m.valid_from,
        "invalid_at": m.invalid_at,
        "source_refs": [r.to_dict() for r in m.source_refs],
        "corroboration": m.corroboration,
        "last_relevant_at": m.last_relevant_at,
        "feedback": m.feedback.value,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def lens_json(lens: LensRow) -> dict:
    return {
        "id": lens.id,
        "name": lens.name,
        "criterion": lens.criterion,
        "entity_type": lens.entity_type,
        "scope": _scope_json(lens.scope),
        "detail_level": lens.detail_level.value,
        "render_mode": lens.render_mode.value,
        "provenance": lens.provenance.value,
        "status": lens.status.value,
        "created_at": lens.created_at,
        "updated_at": lens.updated_at,
    }


def edge_json(e: MemoryEdge) -> dict:
    return {
        "child_id": e.child_id,
        "parent_id": e.parent_id,
        "role": e.role.value,
        "position": e.position,
        "created_at": e.created_at,
    }


def coverage_json(c: CoverageAdvisory) -> dict:
    return {
        "lens_id": c.lens_id,
        "scope_pool": c.scope_pool,
        "member_count": c.member_count,
        "ratio": c.ratio,
        "generic": c.generic,
        "suggestion": c.suggestion,
    }


def claim_block_json(b: RenderedClaim) -> dict:
    return {
        "claim_id": b.claim_id,
        "content": b.content,
        "provenance": b.provenance.value,
        "corroboration": b.corroboration,
        "feedback": b.feedback.value,
        "source_refs": [r.to_dict() for r in b.source_refs],
    }


def group_json(g: ProjectedGroup) -> dict:
    return {
        "subject": g.subject,
        "markdown": g.markdown,
        "synthesized": g.synthesized,
        "blocks": [claim_block_json(b) for b in g.blocks],
    }


def page_json(p: ProjectedPage) -> dict:
    return {
        "lens_id": p.lens_id,
        "detail": p.detail.value,
        "markdown": p.markdown,
        "blocks": [claim_block_json(b) for b in p.blocks],
        "synthesized": p.synthesized,
        "coverage": coverage_json(p.coverage) if p.coverage else None,
        "groups": [group_json(g) for g in p.groups] if p.groups is not None else None,
    }


def ranked_json(r: RankedItem) -> dict:
    return {
        "item": item_json(r.item),
        "order_score": r.order_score,
        "rrf": r.rrf,
        "freshness": r.freshness,
        "provenance_ord": r.provenance_ord,
        "corroboration": r.corroboration,
    }


def _parse_detail(detail: str | None) -> LensDetailLevel | None:
    if detail is None:
        return None
    try:
        return LensDetailLevel(detail)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid detail: {detail}")


def _parse_roles(roles: str | None) -> set[EdgeRole] | None:
    if not roles:
        return None
    try:
        parsed = {EdgeRole(r) for r in roles.split(",") if r}
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid roles: {roles}")
    return parsed or None


async def _require_active_lens(store, lens_id: str) -> LensRow:
    lens = await store.get_lens(lens_id)
    if lens is None or lens.status.value != "active":
        raise HTTPException(status_code=404, detail="lens not found or inactive")
    return lens


# --- 1: list claims/lenses -------------------------------------------


@router.get("/scopes")
async def list_scopes(knowledge: KnowledgeRuntime = Depends(_knowledge)):
    """Scopes that hold active claims (+counts) so the UI can offer a scope switcher."""
    return {"scopes": await knowledge.memory.scopes_with_counts()}


@router.get("/items")
async def list_items(
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    scope_kind: str = "all",
    scope_key: str | None = None,
    subject: str | None = None,
    status: str = "active",
    valid_at: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    scope = _scope_or_all(scope_kind, scope_key)
    # Empty status string => all statuses (store.query(status=None)).
    if status == "":
        status_enum: Status | None = None
    else:
        try:
            status_enum = Status(status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"invalid status: {status}")

    items = await knowledge.memory.query(
        scope=scope, status=status_enum, subject=subject, valid_at=valid_at, limit=limit
    )
    return {"items": [item_json(m) for m in items], "limit": limit}


# --- 2: get one item + provenance edges ------------------------------


@router.get("/items/{item_id}")
async def get_item(item_id: str, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    store = knowledge.memory
    item = await store.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    parents = await store.list_edges(item_id, direction="from")
    children = await store.list_edges(item_id, direction="to")
    return {
        "item": item_json(item),
        "parents": [edge_json(e) for e in parents],
        "children": [edge_json(e) for e in children],
    }


# --- 3: list lenses (with coverage advisory) -------------------------


@router.get("/lenses")
async def list_lenses(
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    scope_kind: str = "all",
    scope_key: str | None = None,
):
    scope = _scope_or_all(scope_kind, scope_key)
    rows = await knowledge.memory_retrieval.lens_registry.list_lenses(scope)
    return {"lenses": [{"lens": lens_json(lens), "coverage": coverage_json(cov)} for lens, cov in rows]}


# --- 4: get a lens page ----------------------------------------------


@router.get("/lenses/{lens_id}/page")
async def get_lens_page(
    lens_id: str,
    response: Response,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    detail: str | None = None,
    refresh: bool = False,
):
    """Non-blocking lens page.

    A clean cache hit returns the materialized page immediately (200). A
    miss/dirty/refresh does NOT run synthesis on the request — it kicks off a
    background generation and returns the live status with HTTP 202 (Accepted) so
    the request never blocks on multi-call synthesis (Lens spec §6; the timeout
    fix). The UI polls `/lenses/{id}/page/status` for progress and re-GETs when
    ready. A missing lens -> 404.
    """
    detail_level = _parse_detail(detail)
    if await knowledge.memory.get_lens(lens_id) is None:
        raise HTTPException(status_code=404, detail="lens not found")

    result = await knowledge.memory_retrieval.lens_generator.ensure(lens_id, detail=detail_level, refresh=refresh)
    if isinstance(result, ProjectedPage):
        return page_json(result)
    response.status_code = 202
    return result.to_json()


@router.get("/lenses/{lens_id}/page/status")
async def get_lens_page_status(
    lens_id: str,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
):
    """Live generation status for a lens page (poll target for the UI progress).

    Returns the current stage (creating/scoring/synthesizing/ready/error), the
    subject + "i/n" while synthesizing, and any error. `status: "idle"` when no
    generation has run (the page is either cached or never requested)."""
    if await knowledge.memory.get_lens(lens_id) is None:
        raise HTTPException(status_code=404, detail="lens not found")
    status = knowledge.memory_retrieval.lens_generator.status(lens_id)
    if status is None:
        return {"lens_id": lens_id, "status": "idle"}
    return status.to_json()


# --- 5a: whole claim-graph (default view) ----------------------------


@router.get("/graph")
async def get_whole_graph(
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    scope_kind: str = "all",
    scope_key: str | None = None,
    subject: str | None = None,
    roles: str | None = None,
    limit: int = Query(default=2000, ge=1, le=5000),
):
    """All active claims + claim↔claim edges among them, across all scopes by default
    (one connected graph; scope is an optional filter). Lenses are never nodes.
    """
    scope = _scope_or_all(scope_kind, scope_key)
    store = knowledge.memory

    role_filter = _parse_roles(roles)
    claims = await store.query(scope=scope, status=Status.ACTIVE, subject=subject, limit=limit)
    nodes = {c.id: c for c in claims}

    edge_keys: set[tuple] = set()
    edges: list[MemoryEdge] = []
    for cid in nodes:
        for e in await store.list_edges(cid, direction="from"):
            if role_filter is not None and e.role not in role_filter:
                continue
            # Claim↔claim edges only; keep edges whose both endpoints are in-scope.
            if e.parent_id not in nodes:
                continue
            key = (e.child_id, e.parent_id, e.role.value)
            if key in edge_keys:
                continue
            edge_keys.add(key)
            edges.append(e)

    return {
        "nodes": [item_json(m) for m in nodes.values()],
        "edges": [edge_json(e) for e in edges],
        "scope": _scope_json(scope) if scope else {"kind": "all", "key": None},
    }


# --- 5: provenance graph (router-side BFS over edges) ----------------


@router.get("/items/{item_id}/graph")
async def get_graph(
    item_id: str,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    direction: str = "both",
    depth: int = 3,
    roles: str | None = None,
):
    if direction not in ("parents", "children", "both"):
        raise HTTPException(status_code=422, detail=f"invalid direction: {direction}")
    store = knowledge.memory
    root = await store.get(item_id)
    if root is None:
        raise HTTPException(status_code=404, detail="item not found")

    role_filter = _parse_roles(roles)

    depth = max(0, min(depth, _MAX_GRAPH_DEPTH))
    dirs = ["from"] if direction == "parents" else ["to"] if direction == "children" else ["from", "to"]

    nodes: dict[str, MemoryItem] = {item_id: root}
    edge_keys: set[tuple] = set()
    edges: list[MemoryEdge] = []
    frontier = {item_id}
    for _ in range(depth):
        if not frontier:
            break
        next_frontier: set[str] = set()
        for node_id in frontier:
            for d in dirs:
                for e in await store.list_edges(node_id, direction=d):
                    if role_filter is not None and e.role not in role_filter:
                        continue
                    key = (e.child_id, e.parent_id, e.role.value)
                    if key in edge_keys:
                        continue
                    edge_keys.add(key)
                    edges.append(e)
                    for touched in (e.child_id, e.parent_id):
                        if touched not in nodes:
                            m = await store.get(touched)
                            if m is not None:
                                nodes[touched] = m
                                next_frontier.add(touched)
        frontier = next_frontier

    return {
        "root_id": item_id,
        "nodes": [item_json(m) for m in nodes.values()],
        "edges": [edge_json(e) for e in edges],
        "depth": depth,
        "direction": direction,
    }


# --- 6: search -------------------------------------------------------


@router.get("/search")
async def search(
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    q: str = Query(..., min_length=1),
    scope_kind: str | None = None,
    scope_key: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    include_inactive: bool = False,
    mode: str = "fts",
):
    if mode == "fts":
        store = knowledge.memory_search or knowledge.memory
        # Omitted scope_kind -> no scope filter (whole pool), so evidence search
        # can surface any claim to Include. An explicit scope_kind still filters.
        scope = _scope(scope_kind, scope_key) if scope_kind else None
        items = await store.search(q, limit=limit, include_inactive=include_inactive, scope=scope)
        return {
            "mode": "fts",
            "items": [item_json(m) for m in items],
            "degraded": not store.has_fts,
        }
    if mode == "retrieve":
        scope = _scope(scope_kind or "user", scope_key)
        ctx: RetrievedContext = await knowledge.memory_retrieval.retrieve(Retrieval(goal=q, scope=scope))
        return {
            "mode": "retrieve",
            "rendered": ctx.rendered,
            "items": [ranked_json(r) for r in ctx.items],
            "degraded": ctx.degraded,
            "diagnostics": ctx.diagnostics,
        }
    raise HTTPException(status_code=422, detail=f"invalid mode: {mode}")


# --- 7: lens page write-back -----------------------------------------


@router.post("/lenses/{lens_id}/writeback")
async def writeback(
    lens_id: str,
    body: WriteBackOpsBody,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
):
    store = knowledge.memory
    await _require_active_lens(store, lens_id)

    ops: list[PageEditOp] = []
    for op in body.ops:
        kind = PageEditKind(op.kind)
        if kind in (PageEditKind.EDIT, PageEditKind.REJECT, PageEditKind.ACCEPT, PageEditKind.INCLUDE) and not op.claim_id:
            raise HTTPException(status_code=422, detail=f"{op.kind} requires claim_id")
        if kind is PageEditKind.EDIT_CRITERION and not op.new_text:
            raise HTTPException(status_code=422, detail=f"{op.kind} requires new_text")
        ops.append(PageEditOp(kind=kind, claim_id=op.claim_id, new_text=op.new_text))

    result: WriteBackResult = await knowledge.memory_retrieval.lens_writeback.apply(lens_id, ops)
    return {
        "applied": [{"kind": k.value, "id": cid} for k, cid in result.applied],
        "rejected": [
            {
                "op": {"kind": o.kind.value, "claim_id": o.claim_id, "new_text": o.new_text},
                "reason": reason,
            }
            for o, reason in result.rejected
        ],
        "rederive_triggered": result.rederive_triggered,
    }


# --- 8: lens lifecycle (admin) ---------------------------------------


@router.post("/lenses/draft")
async def draft_lens(body: DraftLensBody, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    scope = _scope(body.scope_kind, body.scope_key)
    try:
        markdown = await knowledge.memory_retrieval.lens_registry.draft_lens(body.name, scope)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"markdown": markdown}


@router.post("/lenses")
async def create_lens(body: CreateLensBody, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    if body.definition_markdown is not None:
        try:
            lens = await knowledge.memory_retrieval.lens_registry.create_lens_from_markdown(body.definition_markdown)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return {"lens": lens_json(lens)}
    if body.name is None:
        raise HTTPException(status_code=422, detail="name or definition_markdown required")
    scope = _scope(body.scope_kind, body.scope_key)
    lens = await knowledge.memory_retrieval.lens_registry.create_lens(
        body.name,
        body.criterion,
        scope,
        render_mode=LensRenderMode(body.render_mode),
    )
    return {"lens": lens_json(lens)}


@router.put("/lenses/{lens_id}/render_mode")
async def set_render_mode(
    lens_id: str,
    body: SetLensRenderModeBody,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
):
    try:
        lens = await knowledge.memory_retrieval.lens_registry.set_render_mode(lens_id, LensRenderMode(body.render_mode))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"lens": lens_json(lens)}


@router.put("/lenses/{lens_id}/criterion")
async def edit_criterion(
    lens_id: str,
    body: EditCriterionBody,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
):
    try:
        lens = await knowledge.memory_retrieval.lens_registry.edit_criterion(lens_id, body.criterion)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"lens": lens_json(lens)}


@router.post("/lenses/{lens_id}/split")
async def split_lens(
    lens_id: str,
    body: SplitLensBody,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
):
    into = [(c.name, c.criterion) for c in body.into]
    try:
        children = await knowledge.memory_retrieval.lens_registry.split_lens(
            lens_id, into, archive_parent=body.archive_parent
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"children": [lens_json(c) for c in children]}


@router.post("/lenses/merge")
async def merge_lenses(body: MergeLensBody, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    # scope is validated for symmetry; merge re-derives scope from the inputs.
    _scope(body.scope_kind, body.scope_key)
    try:
        lens = await knowledge.memory_retrieval.lens_registry.merge_lenses(body.lens_ids, body.name, body.criterion)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"lens": lens_json(lens)}


@router.delete("/lenses/{lens_id}")
async def delete_lens(lens_id: str, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    deleted = await knowledge.memory_retrieval.lens_registry.delete_lens(lens_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="lens not found")
    return {"deleted": deleted}


@router.post("/remember")
async def remember(body: RememberBody, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    """Manual user-authored write — the desktop 'pin to memory' handoff. Enters
    the same admit→write seam as the remember() tool (USER_AUTHORED, bypass_admit)."""
    seam = knowledge.memory_service
    if not isinstance(seam, WriteSeam):
        raise HTTPException(status_code=503, detail="Memory write is not available")
    outcome = await seam.admit_and_write(_pin_write_request(body.fact, body.project_id))
    if not outcome.written and outcome.item_id is None and "Already known" not in outcome.reason:
        raise HTTPException(status_code=422, detail=outcome.reason)
    return {"written": outcome.written, "item_id": outcome.item_id, "reason": outcome.reason}
