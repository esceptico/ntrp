"""Slices router — a project's automations/sessions/asks grouped under a
`slice_key` (mirrors project_id). Wired onto app.state (SliceService is a
plain constructor with injected callables, not a FastAPI Depends chain)."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/slices", tags=["slices"])


class ResolveBody(BaseModel):
    state: Literal["dismissed", "done", "snoozed"]
    snoozed_until: str | None = None


class AutonomyBody(BaseModel):
    autonomy: Literal["observe", "act"]


class CreateBody(BaseModel):
    key: str
    title: str
    page_path: str


def _svc(request: Request):
    return request.app.state.slice_service


@router.get("")
async def list_slices(request: Request):
    await request.app.state.hydrate_slice_snapshot()
    svc = _svc(request)
    svc.refresh_mechanical()
    return svc.overview()


@router.get("/{key}")
async def slice_detail(request: Request, key: str):
    await request.app.state.hydrate_slice_snapshot()
    try:
        return _svc(request).detail(key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{key}/asks/{ask_id}/resolve")
async def resolve_ask(request: Request, key: str, ask_id: str, body: ResolveBody):
    try:
        ask = _svc(request).resolve_ask(ask_id, body.state, body.snoozed_until)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await request.app.state.emit_slices_changed([key])
    return ask


@router.put("/{key}")
async def update_slice_autonomy(request: Request, key: str, body: AutonomyBody):
    try:
        slice_ = _svc(request).update_autonomy(key, body.autonomy)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await request.app.state.emit_slices_changed([key])
    return slice_


@router.post("")
async def create_slice(request: Request, body: CreateBody):
    try:
        slice_ = _svc(request).create_slice(body.key, body.title, body.page_path)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await request.app.state.emit_slices_changed([body.key])
    return slice_
