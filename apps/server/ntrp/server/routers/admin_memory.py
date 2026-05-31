from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ntrp.memory.items_store import OutcomeEventInsert
from ntrp.memory.learnings import Correction, LearningsStore
from ntrp.memory.lens_author import LensAuthorError
from ntrp.memory.lenses import load_lenses
from ntrp.memory.pattern_finder import PatternFinder
from ntrp.memory.skill_inducer import (
    ProposalDraftGone,
    ProposalNotFound,
    ProposalStateError,
    SkillInducer,
    SkillSlugCollision,
)
from ntrp.server.deps import require_lens_author, require_lens_pass, require_memory, require_pattern_finder

router = APIRouter(prefix="/admin/memory", tags=["admin"])


class PatternFinderRunRequest(BaseModel):
    pass_: int | str | None = Field(default=None, alias="pass")
    window_days: int | None = Field(default=None, ge=1, le=90)
    scope: str = "user"
    limit: int = Field(default=500, ge=1, le=1000)


class ContradictionScanRequest(BaseModel):
    scope: str = "user"
    window_days: int = Field(default=30, ge=1, le=90)
    limit: int = Field(default=500, ge=1, le=1000)


class SkillInducerRunRequest(BaseModel):
    window_days: int = Field(default=30, ge=1, le=90)
    scope: str = "user"
    limit: int = Field(default=500, ge=1, le=1000)


class ProposalRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class LensGenerateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    scope: str = "user"


class LensUpdateRequest(BaseModel):
    markdown: str = Field(min_length=1, max_length=8000)
    scope: str = "user"


class ItemUpdateRequest(BaseModel):
    content: str | None = Field(default=None, max_length=20000)
    title: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = None
    scope: str | None = None
    status: str | None = None
    invalid_at: str | None = None


class SkillEnabledRequest(BaseModel):
    enabled: bool


_ALLOWED_OUTCOMES = {"helpful", "harmful", "irrelevant", "corrected", "task_success", "task_failure"}


class ItemOutcomeRequest(BaseModel):
    outcome: str
    source: str = Field(default="api", max_length=200)
    usage_event_id: int | None = None
    run_id: str | None = Field(default=None, max_length=200)


@router.post("/pattern-finder/run")
async def run_pattern_finder(
    request: PatternFinderRunRequest,
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    selected_pass = request.pass_
    if selected_pass is None:
        result = await pattern_finder.run_pass1(
            window_days=request.window_days or 7,
            scope=request.scope,
            limit=request.limit,
        )
        return result.to_dict()
    if selected_pass in {1, "1"}:
        result = await pattern_finder.run_pass1(
            window_days=request.window_days or 7,
            scope=request.scope,
            limit=request.limit,
        )
        return {"pass1": result.to_dict()}
    if selected_pass in {2, "2"}:
        result = await pattern_finder.run_pass2(
            window_days=request.window_days or 30,
            scope=request.scope,
            limit=request.limit,
        )
        return {"pass2": result.to_dict()}
    if selected_pass == "both":
        pass1 = await pattern_finder.run_pass1(
            window_days=request.window_days or 7,
            scope=request.scope,
            limit=request.limit,
        )
        pass2 = await pattern_finder.run_pass2(
            window_days=request.window_days or 30,
            scope=request.scope,
            limit=request.limit,
        )
        return {"pass1": pass1.to_dict(), "pass2": pass2.to_dict()}
    raise HTTPException(status_code=400, detail="pass must be 1, 2, or 'both'")


@router.post("/skill-inducer/run")
async def run_skill_inducer(
    request: SkillInducerRunRequest,
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    result = await _require_skill_inducer(pattern_finder).run(
        window_days=request.window_days,
        scope=request.scope,
        limit=request.limit,
    )
    return result.to_dict()


@router.get("/proposals")
async def list_memory_proposals(
    status: str = Query(default="open"),
    scope: str = Query(default="user"),
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    proposals = await _require_skill_inducer(pattern_finder).list_proposals(status=status, scope=scope)
    return {"proposals": proposals}


@router.post("/proposals/{proposal_id}/approve")
async def approve_memory_proposal(
    proposal_id: str,
    slug: str | None = Query(default=None),
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    try:
        return await _require_skill_inducer(pattern_finder).approve_proposal(proposal_id, slug=slug)
    except ProposalDraftGone as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except (ProposalStateError, SkillSlugCollision) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProposalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/reject")
async def reject_memory_proposal(
    proposal_id: str,
    request: ProposalRejectRequest,
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    try:
        return await _require_skill_inducer(pattern_finder).reject_proposal(proposal_id, reason=request.reason)
    except ProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProposalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/contradictions/scan")
async def scan_contradictions(
    request: ContradictionScanRequest,
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    watcher = _require_contradiction_watcher(pattern_finder)
    result = await watcher.scan_window(scope=request.scope, window_days=request.window_days, limit=request.limit)
    candidates = getattr(result, "candidates", result)
    return {
        "scope": request.scope,
        "window_days": request.window_days,
        "claims_scanned": getattr(result, "claims_scanned", len(candidates)),
        "contradictions_found": len(candidates),
    }


@router.post("/contradictions/{child_id}/{parent_id}/undo")
async def undo_contradiction(
    child_id: str,
    parent_id: str,
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    watcher = _require_contradiction_watcher(pattern_finder)
    try:
        result = await watcher.undo(child_id=child_id, parent_id=parent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not result.get("already_undone"):
        LearningsStore().record(
            Correction(
                adjudicator="contradiction",
                action="not_same",
                summary=f"User undid the contradiction between {child_id} and {parent_id}.",
                subjects=(child_id, parent_id),
                reason="contradiction undone via admin",
            )
        )
    return result


def _require_contradiction_watcher(pattern_finder: PatternFinder) -> Any:
    watcher = getattr(pattern_finder, "contradiction_watcher", None)
    if watcher is None:
        raise HTTPException(status_code=503, detail="Contradiction watcher is unavailable")
    return watcher


def _require_skill_inducer(pattern_finder: PatternFinder) -> SkillInducer:
    inducer = getattr(pattern_finder, "skill_inducer", None)
    if inducer is not None:
        return inducer
    try:
        inducer = SkillInducer(
            repo=pattern_finder.repo,
            draft_client=pattern_finder.summary_client,
            embedder=pattern_finder.embedder,
        )
    except AttributeError as exc:
        raise HTTPException(status_code=503, detail="Skill inducer is unavailable") from exc
    pattern_finder.skill_inducer = inducer
    return inducer


_ALLOWED_KINDS = {"episode", "observation", "claim", "skill", "proposal", "artifact_ref", "entity", "directory"}
_ALLOWED_STATUSES = {"active", "superseded", "archived"}
_ALLOWED_VALIDITY = {"all", "current", "future", "expired"}
_GRAPH_EDGE_ROLES = {"step", "evidence", "contradicts", "supersedes", "similar_to", "member_of"}


def _serialize_item(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "content": item.content,
        "title": item.title,
        "provenance": item.provenance,
        "source_refs": item.source_refs,
        "confidence": item.confidence,
        "status": item.status,
        "valid_from": item.valid_from.isoformat() if item.valid_from else None,
        "invalid_at": item.invalid_at.isoformat() if item.invalid_at else None,
        "scope": item.scope,
        "tags": item.tags,
        "artifact_ref": item.artifact_ref,
        "usage": item.usage,
        "feedback": item.feedback,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "has_embedding": item.embedding is not None,
    }


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid datetime: {value}") from exc


def _parse_csv(value: str | None, allowed: set[str], field: str) -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    bad = [v for v in items if v not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: {', '.join(bad)}")
    return items or None


def _parse_validity(value: str | None) -> str | None:
    if not value or value == "all":
        return None
    if value not in _ALLOWED_VALIDITY:
        raise HTTPException(status_code=400, detail=f"Invalid validity: {value}")
    return value


def _serialize_edge(edge: Any) -> dict[str, Any]:
    return {
        "child_id": edge.child_id,
        "parent_id": edge.parent_id,
        "role": edge.role,
        "order": edge.order,
        "created_at": edge.created_at.isoformat() if edge.created_at else None,
    }


@router.get("/today")
async def memory_today(
    scope: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    memory=Depends(require_memory),
):
    repo = memory.memory.items
    pending_proposals = [
        item
        for item in await repo.list_items(kinds=["proposal"], statuses=["active"], scope=scope, limit=limit * 3)
        if "proposal-status:open" in item.tags
    ][:limit]
    new_skills = await repo.list_items(kinds=["skill"], statuses=["active"], scope=scope, limit=limit)
    low_confidence_claims = [
        item
        for item in await repo.list_items(kinds=["claim"], statuses=["active"], scope=scope, limit=limit * 2)
        if item.confidence < 0.6
    ][:limit]
    superseded_claims = await repo.list_items(kinds=["claim"], statuses=["superseded"], scope=scope, limit=limit)
    return {
        "new_skills": [_serialize_item(item) for item in new_skills],
        "pending_proposals": [_serialize_item(item) for item in pending_proposals],
        "low_confidence_claims": [_serialize_item(item) for item in low_confidence_claims],
        "recent_corrections": [_serialize_item(item) for item in superseded_claims],
    }


@router.get("/skills")
async def list_memory_skills(
    scope: str | None = Query(default=None),
    include_disabled: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=200),
    memory=Depends(require_memory),
):
    statuses = ["active", "archived"] if include_disabled else ["active"]
    skills = await memory.memory.items.list_items(kinds=["skill"], statuses=statuses, scope=scope, limit=limit)
    return {"skills": [_serialize_item(item) for item in skills]}


@router.post("/skills/{skill_id}/enabled")
async def set_memory_skill_enabled(
    skill_id: str,
    request: SkillEnabledRequest,
    memory=Depends(require_memory),
):
    repo = memory.memory.items
    item = await repo.get_item(skill_id)
    if item is None or item.kind != "skill":
        raise HTTPException(status_code=404, detail="Skill memory item not found")
    status = "active" if request.enabled else "archived"
    await repo.conn.execute(
        "UPDATE memory_items SET status = ?, invalid_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, skill_id),
    )
    await repo.conn.commit()
    updated = await repo.get_item(skill_id)
    return {"skill": _serialize_item(updated)}


@router.get("/graph")
async def get_memory_graph(
    scope: str | None = Query(default=None),
    include_unlinked: bool = Query(default=False),
    memory=Depends(require_memory),
):
    repo = memory.memory.items
    items = await repo.list_graph_items(include_unlinked=include_unlinked, scope=scope)
    node_ids = {item.id for item in items}
    edges = [
        edge
        for edge in await repo.list_all_edges()
        if edge.role in _GRAPH_EDGE_ROLES and edge.child_id in node_ids and edge.parent_id in node_ids
    ]
    return {
        "nodes": [_serialize_item(item) for item in items],
        "edges": [_serialize_edge(edge) for edge in edges],
        "include_unlinked": include_unlinked,
    }


@router.get("/directories")
async def list_memory_directories(
    scope: str | None = Query(default=None),
    memory=Depends(require_memory),
):
    repo = memory.memory.items
    lenses = {lens.slug: lens for lens in load_lenses()}
    directories = await repo.list_directories(scope=scope)
    out = []
    for directory in directories:
        slug = next((tag.split(":", 1)[1] for tag in directory.tags if tag.startswith("lens:")), None)
        lens = lenses.get(slug) if slug else None
        members = await repo.list_directory_members(directory.id)
        markdown = (
            f"---\ndirectory: {lens.directory}\nentity_type: {lens.entity_type}\n---\n{lens.body}\n" if lens else None
        )
        out.append(
            {
                "directory": _serialize_item(directory),
                "slug": slug,
                "entity_type": lens.entity_type if lens else None,
                "markdown": markdown,
                "members": [_serialize_item(member) for member in members],
            }
        )
    return {"directories": out}


@router.get("/lenses")
async def list_memory_lenses():
    lenses = load_lenses()
    return {
        "lenses": [
            {"slug": lens.slug, "directory": lens.directory, "entity_type": lens.entity_type, "path": str(lens.path)}
            for lens in lenses
        ]
    }


@router.put("/lenses/{slug}")
async def update_memory_lens(slug: str, request: LensUpdateRequest, lens_author=Depends(require_lens_author)):
    try:
        return await lens_author.update_lens(slug, request.markdown, scope=request.scope)
    except LensAuthorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/lenses/{slug}")
async def delete_memory_lens(slug: str, lens_author=Depends(require_lens_author)):
    return await lens_author.delete_lens(slug)


@router.post("/lenses/run")
async def run_lens_pass(
    scope: str = Query(default="user"),
    lens_pass=Depends(require_lens_pass),
):
    result = await lens_pass.run(scope=scope)
    return result.to_dict()


@router.post("/lenses/generate")
async def generate_lens(request: LensGenerateRequest, lens_author=Depends(require_lens_author)):
    try:
        proposal = await lens_author.propose(request.query, scope=request.scope)
    except LensAuthorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "proposal_id": proposal.proposal_id,
        "slug": proposal.slug,
        "directory": proposal.directory,
        "entity_type": proposal.entity_type,
        "markdown": proposal.markdown,
    }


@router.get("/lenses/proposals")
async def list_lens_proposals(scope: str | None = Query(default=None), lens_author=Depends(require_lens_author)):
    return {"proposals": await lens_author.list_proposals(scope=scope)}


@router.post("/lenses/proposals/{proposal_id}/approve")
async def approve_lens_proposal(
    proposal_id: str,
    slug: str | None = Query(default=None),
    scope: str = Query(default="user"),
    lens_author=Depends(require_lens_author),
):
    try:
        return await lens_author.approve(proposal_id, slug=slug, scope=scope)
    except LensAuthorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/lenses/proposals/{proposal_id}/reject")
async def reject_lens_proposal(proposal_id: str, lens_author=Depends(require_lens_author)):
    try:
        return await lens_author.reject(proposal_id)
    except LensAuthorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/items/{item_id}/graph")
async def get_memory_item_graph(
    item_id: str,
    depth: int = Query(default=3, ge=0, le=5),
    direction: str = Query(default="both", pattern="^(parents|children|both)$"),
    memory=Depends(require_memory),
):
    repo = memory.memory.items
    root = await repo.get_item(item_id)
    if root is None:
        raise HTTPException(status_code=404, detail="Memory item not found")

    nodes = {root.id: root}
    edge_map: dict[tuple[str, str, str], Any] = {}
    frontier = {root.id}
    visited = {root.id}
    for _ in range(depth):
        next_frontier: set[str] = set()
        for node_id in frontier:
            incident = []
            if direction in {"parents", "both"}:
                incident.extend(await repo.list_parent_edges(node_id))
            if direction in {"children", "both"}:
                incident.extend(await repo.list_child_edges(node_id))
            for edge in incident:
                edge_map[(edge.child_id, edge.parent_id, edge.role)] = edge
                other_id = edge.parent_id if edge.child_id == node_id else edge.child_id
                if other_id not in nodes:
                    other = await repo.get_item(other_id)
                    if other is not None:
                        nodes[other_id] = other
                if other_id not in visited:
                    visited.add(other_id)
                    next_frontier.add(other_id)
        frontier = next_frontier
        if not frontier:
            break

    return {
        "root_id": item_id,
        "nodes": [_serialize_item(item) for item in nodes.values()],
        "edges": [_serialize_edge(edge) for edge in edge_map.values() if edge.role in _GRAPH_EDGE_ROLES],
        "depth": depth,
        "direction": direction,
    }


@router.get("/items")
async def list_memory_items(
    kinds: str | None = Query(default=None, description="Comma-separated kinds"),
    statuses: str | None = Query(default="active", description="Comma-separated statuses"),
    scope: str | None = Query(default=None),
    query: str | None = Query(default=None, description="FTS query; if provided overrides ordering"),
    validity: str | None = Query(default="all", description="all/current/future/expired"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    memory=Depends(require_memory),
):
    repo = memory.memory.items
    kind_list = _parse_csv(kinds, _ALLOWED_KINDS, "kinds")
    status_list = _parse_csv(statuses, _ALLOWED_STATUSES, "statuses")
    validity_filter = _parse_validity(validity)
    if query:
        items = await repo.search_items_fts(
            query,
            kinds=kind_list,
            statuses=status_list,
            scope=scope,
            validity=validity_filter,
            limit=limit,
        )
        total = len(items)
    else:
        items = await repo.list_items(
            kinds=kind_list,
            statuses=status_list,
            scope=scope,
            validity=validity_filter,
            limit=limit,
            offset=offset,
        )
        total = await repo.count_items(
            kinds=kind_list,
            statuses=status_list,
            scope=scope,
            validity=validity_filter,
        )
    return {
        "items": [_serialize_item(it) for it in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/items/{item_id}")
async def get_memory_item(item_id: str, memory=Depends(require_memory)):
    repo = memory.memory.items
    item = await repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    parent_edges = await repo.list_parent_edges(item_id)
    parents = []
    for edge in parent_edges:
        parent_item = await repo.get_item(edge.parent_id)
        parents.append(
            {
                "parent_id": edge.parent_id,
                "role": edge.role,
                "order": edge.order,
                "created_at": edge.created_at.isoformat() if edge.created_at else None,
                "parent": _serialize_item(parent_item) if parent_item else None,
            }
        )
    return {
        "item": _serialize_item(item),
        "parents": parents,
    }


@router.post("/items/{item_id}/outcome")
async def record_memory_item_outcome(item_id: str, request: ItemOutcomeRequest, memory=Depends(require_memory)):
    if request.outcome not in _ALLOWED_OUTCOMES:
        raise HTTPException(status_code=422, detail=f"invalid outcome: {request.outcome}")
    repo = memory.memory.items
    item = await repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    event_id = await repo.record_outcome(
        OutcomeEventInsert(
            item_id=item_id,
            outcome=request.outcome,
            source=request.source,
            usage_event_id=request.usage_event_id,
            run_id=request.run_id,
        )
    )
    return {"event_id": event_id, "item": _serialize_item(await repo.get_item(item_id))}


@router.put("/items/{item_id}")
async def update_memory_item(item_id: str, request: ItemUpdateRequest, memory=Depends(require_memory)):
    repo = memory.memory.items
    item = await repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")

    content = request.content if request.content is not None else item.content
    if not content.strip():
        raise HTTPException(status_code=422, detail="content cannot be empty")
    scope = request.scope if request.scope is not None else item.scope
    status = request.status if request.status is not None else item.status
    if status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")

    invalid_at = item.invalid_at
    if request.invalid_at is not None:
        invalid_at = None if request.invalid_at == "" else _parse_dt(request.invalid_at)

    embedding = None
    if request.content is not None and request.content != item.content:
        embedding = await memory.memory.embedder.embed_one(content)

    await repo.update_item(
        item_id,
        content=content,
        title=request.title if request.title is not None else item.title,
        confidence=request.confidence if request.confidence is not None else item.confidence,
        tags=request.tags if request.tags is not None else item.tags,
        scope=scope,
        status=status,
        invalid_at=invalid_at,
        embedding=embedding,
    )
    updated = await repo.get_item(item_id)
    _record_item_edit_learning(item, updated)
    return {"item": _serialize_item(updated)}


_EDIT_ADJUDICATOR_BY_KIND = {"claim": "dedup", "entity": "entity_link"}


def _record_item_edit_learning(before: Any, after: Any) -> None:
    adjudicator = _EDIT_ADJUDICATOR_BY_KIND.get(before.kind)
    if adjudicator is None or before.content == after.content:
        return
    LearningsStore().record(
        Correction(
            adjudicator=adjudicator,
            action="edit",
            summary=f"User edited {before.kind} {before.id}.",
            subjects=(before.id,),
            proposed=before.content,
            correct=after.content,
            reason="item edited via admin",
        )
    )


@router.delete("/items/{item_id}")
async def delete_memory_item(item_id: str, memory=Depends(require_memory)):
    repo = memory.memory.items
    item = await repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    await repo.delete_item(item_id)
    return {"deleted": True}


@router.get("/stats")
async def memory_stats(memory=Depends(require_memory)):
    repo = memory.memory.items
    counts: dict[str, dict[str, int]] = {}
    for kind in sorted(_ALLOWED_KINDS):
        counts[kind] = {}
        for status in sorted(_ALLOWED_STATUSES):
            counts[kind][status] = await repo.count_items(kinds=[kind], statuses=[status])
    return {"counts": counts}
