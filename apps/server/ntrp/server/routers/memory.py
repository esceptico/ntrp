"""Memory UI router (Stage-5) — read + structured write-back over the frozen store.

Thin HTTP surface over `MemoryStore` (reads), `LensProjector`/`LensService`
(lens page + lifecycle), `LensWriteBack` (anchored page edits), and
`MemoryPipeline.retrieve` (ranked egress). No new store methods, no invariant
change: every route is a composition of existing pipeline/store calls. The full
contract lives in routers/MEMORY_UI_CONTRACT.md.

Wiring: `require_knowledge_runtime` → `KnowledgeRuntime`. Reads use
`knowledge.memory` (the store); lens/page/writeback/retrieve use
`knowledge.memory_retrieval` (the pipeline, exposing `.lens_service`,
`.lens_projector`, `.lens_writeback`, `.retrieve`). Every route guards
`knowledge.memory_ready` → 503 when the pipeline is not up.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ntrp.memory.models import (
    EdgeRole,
    Kind,
    LensDetailLevel,
    MemoryEdge,
    MemoryItem,
    Scope,
    ScopeKind,
    Status,
)
from ntrp.memory.pipeline.types import (
    CoverageAdvisory,
    PageEditKind,
    PageEditOp,
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
    EditCriterionBody,
    MergeLensBody,
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


def _scope_json(scope: Scope) -> dict:
    return {"kind": scope.kind.value, "key": scope.key}


def item_json(m: MemoryItem) -> dict:
    return {
        "id": m.id,
        "kind": m.kind.value,
        "content": m.content,
        "scope": _scope_json(m.scope),
        "provenance": m.provenance.value,
        "status": m.status.value,
        "valid_from": m.valid_from,
        "invalid_at": m.invalid_at,
        "source_refs": [r.to_dict() for r in m.source_refs],
        "corroboration": m.corroboration,
        "last_relevant_at": m.last_relevant_at,
        "feedback": m.feedback.value,
        "lens_name": m.lens_name,
        "lens_criterion": m.lens_criterion,
        "lens_kind": m.lens_kind,
        "lens_detail_level": m.lens_detail_level.value if m.lens_detail_level else None,
        "lens_exclusive": m.lens_exclusive,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
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


def page_json(p: ProjectedPage) -> dict:
    return {
        "lens_id": p.lens_id,
        "detail": p.detail.value,
        "markdown": p.markdown,
        "blocks": [claim_block_json(b) for b in p.blocks],
        "synthesized": p.synthesized,
        "coverage": coverage_json(p.coverage) if p.coverage else None,
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


async def _require_active_lens(store, lens_id: str) -> MemoryItem:
    lens = await store.get(lens_id)
    if lens is None or lens.kind is not Kind.LENS or lens.status is not Status.ACTIVE:
        raise HTTPException(status_code=404, detail="lens not found or inactive")
    return lens


# --- 1: list claims/lenses -------------------------------------------


@router.get("/items")
async def list_items(
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    scope_kind: str = "user",
    scope_key: str | None = None,
    kind: str = "claim",
    status: str = "active",
    valid_at: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    scope = _scope(scope_kind, scope_key)
    try:
        kind_enum = Kind(kind)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid kind: {kind}")
    # Empty status string => all statuses (store.query(status=None)).
    if status == "":
        status_enum: Status | None = None
    else:
        try:
            status_enum = Status(status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"invalid status: {status}")

    items = await knowledge.memory.query(
        kind=kind_enum, scope=scope, status=status_enum, valid_at=valid_at, limit=limit
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
    scope_kind: str = "user",
    scope_key: str | None = None,
):
    scope = _scope(scope_kind, scope_key)
    rows = await knowledge.memory_retrieval.lens_service.list_lenses(scope)
    return {
        "lenses": [
            {"lens": item_json(lens), "coverage": coverage_json(cov)} for lens, cov in rows
        ]
    }


# --- 4: get a lens page ----------------------------------------------


@router.get("/lenses/{lens_id}/page")
async def get_lens_page(
    lens_id: str,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
    detail: str | None = None,
    refresh: bool = False,
):
    detail_level: LensDetailLevel | None = None
    if detail is not None:
        try:
            detail_level = LensDetailLevel(detail)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"invalid detail: {detail}")

    page = await knowledge.memory_retrieval.lens_projector.project(
        lens_id, detail=detail_level, refresh=refresh
    )
    # project() returns an empty page for missing/inactive lenses; map empty +
    # store.get is None -> 404. An active lens with zero members returns a
    # non-empty header markdown and is NOT a 404.
    if not page.markdown and not page.blocks:
        if await knowledge.memory.get(lens_id) is None:
            raise HTTPException(status_code=404, detail="lens not found")
    return page_json(page)


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

    role_filter: set[EdgeRole] | None = None
    if roles:
        try:
            role_filter = {EdgeRole(r) for r in roles.split(",") if r}
        except ValueError:
            raise HTTPException(status_code=422, detail=f"invalid roles: {roles}")
        if not role_filter:
            role_filter = None

    depth = max(0, min(depth, _MAX_GRAPH_DEPTH))
    dirs = (
        ["from"] if direction == "parents" else ["to"] if direction == "children" else ["from", "to"]
    )

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
    scope_kind: str = "user",
    scope_key: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    include_inactive: bool = False,
    mode: str = "fts",
):
    if mode == "fts":
        store = knowledge.memory
        items = await store.search(q, limit=limit, include_inactive=include_inactive)
        return {
            "mode": "fts",
            "items": [item_json(m) for m in items],
            "degraded": not store.has_fts,
        }
    if mode == "retrieve":
        scope = _scope(scope_kind, scope_key)
        ctx: RetrievedContext = await knowledge.memory_retrieval.retrieve(
            Retrieval(goal=q, scope=scope, kinds=(Kind.CLAIM,))
        )
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
        if kind in (PageEditKind.EDIT, PageEditKind.REJECT, PageEditKind.ACCEPT) and not op.claim_id:
            raise HTTPException(status_code=422, detail=f"{op.kind} requires claim_id")
        if kind in (PageEditKind.ADD, PageEditKind.EDIT_CRITERION) and not op.new_text:
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


@router.post("/lenses")
async def create_lens(body: CreateLensBody, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    scope = _scope(body.scope_kind, body.scope_key)
    lens = await knowledge.memory_retrieval.lens_service.create_lens(
        body.name, body.criterion, scope, lens_kind=body.lens_kind
    )
    return {"lens": item_json(lens)}


@router.put("/lenses/{lens_id}/criterion")
async def edit_criterion(
    lens_id: str,
    body: EditCriterionBody,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
):
    try:
        lens = await knowledge.memory_retrieval.lens_service.edit_criterion(lens_id, body.criterion)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"lens": item_json(lens)}


@router.post("/lenses/{lens_id}/split")
async def split_lens(
    lens_id: str,
    body: SplitLensBody,
    knowledge: KnowledgeRuntime = Depends(_knowledge),
):
    into = [(c.name, c.criterion) for c in body.into]
    try:
        children = await knowledge.memory_retrieval.lens_service.split_lens(
            lens_id, into, archive_parent=body.archive_parent
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"children": [item_json(c) for c in children]}


@router.post("/lenses/merge")
async def merge_lenses(body: MergeLensBody, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    # scope is validated for symmetry; merge re-derives scope from the inputs.
    _scope(body.scope_kind, body.scope_key)
    try:
        lens = await knowledge.memory_retrieval.lens_service.merge_lenses(
            body.lens_ids, body.name, body.criterion
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"lens": item_json(lens)}


@router.delete("/lenses/{lens_id}")
async def delete_lens(lens_id: str, knowledge: KnowledgeRuntime = Depends(_knowledge)):
    archived = await knowledge.memory_retrieval.lens_service.delete_lens(lens_id)
    if not archived:
        raise HTTPException(status_code=404, detail="lens not found or already inactive")
    return {"archived": archived}
