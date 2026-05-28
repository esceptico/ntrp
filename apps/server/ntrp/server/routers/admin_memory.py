from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ntrp.memory.pattern_finder import PatternFinder
from ntrp.memory.skill_inducer import (
    ProposalDraftGone,
    ProposalNotFound,
    ProposalStateError,
    SkillInducer,
    SkillSlugCollision,
)
from ntrp.server.deps import require_pattern_finder

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
        return await watcher.undo(child_id=child_id, parent_id=parent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
