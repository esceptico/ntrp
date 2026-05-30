"""Learnings router.

Read/write access to the user-editable "learnings" markdown — the corrections the
user has made to automated memory decisions (see :mod:`ntrp.memory.learnings`). The
files are the source of truth; these endpoints let the UI list, view, hand-edit, and
append entries.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ntrp.memory.learnings import ADJUDICATORS, Correction, LearningsStore

router = APIRouter(prefix="/admin/memory/learnings", tags=["admin"])


class CorrectionRecordRequest(BaseModel):
    action: str = Field(max_length=32)
    summary: str = Field(min_length=1, max_length=500)
    subjects: list[str] = Field(default_factory=list)
    proposed: str = Field(default="", max_length=500)
    correct: str = Field(default="", max_length=500)
    reason: str = Field(default="", max_length=500)


class LearningsUpdateRequest(BaseModel):
    markdown: str = Field(min_length=1, max_length=20000)


def _require_known(adjudicator: str) -> None:
    if adjudicator not in ADJUDICATORS:
        raise HTTPException(status_code=404, detail=f"unknown adjudicator: {adjudicator}")


@router.get("")
async def list_learnings():
    store = LearningsStore()
    return {"adjudicators": sorted(ADJUDICATORS), "present": store.list_adjudicators()}


@router.get("/{adjudicator}")
async def get_learnings(adjudicator: str):
    _require_known(adjudicator)
    return {"adjudicator": adjudicator, "markdown": LearningsStore().load(adjudicator)}


@router.put("/{adjudicator}")
async def put_learnings(adjudicator: str, request: LearningsUpdateRequest):
    _require_known(adjudicator)
    store = LearningsStore()
    path = store.path(adjudicator)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(request.markdown, encoding="utf-8")
    return {"adjudicator": adjudicator, "markdown": store.load(adjudicator)}


@router.post("/{adjudicator}")
async def record_learning(adjudicator: str, request: CorrectionRecordRequest):
    _require_known(adjudicator)
    store = LearningsStore()
    store.record(
        Correction(
            adjudicator=adjudicator,
            action=request.action,
            summary=request.summary,
            subjects=tuple(request.subjects),
            proposed=request.proposed,
            correct=request.correct,
            reason=request.reason,
        )
    )
    return {"ok": True, "markdown": store.load(adjudicator)}
