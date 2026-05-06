from fastapi import APIRouter, Depends, HTTPException

from ntrp.agent import Role
from ntrp.constants import HISTORY_MESSAGE_LIMIT
from ntrp.core.content import blocks_to_text
from ntrp.server.deps import require_session_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    BranchRequest,
    ClearSessionRequest,
    CreateSessionRequest,
    RenameSessionRequest,
    RevertRequest,
    SessionResponse,
)
from ntrp.services.session import SessionService

router = APIRouter(tags=["session"])


@router.get("/session/history")
async def get_session_history(
    svc: SessionService = Depends(require_session_service),
    runtime: Runtime = Depends(get_runtime),
    session_id: str | None = None,
):
    data = await svc.load(session_id)
    if not data:
        return {"messages": [], "active_run_id": None}

    # Active-run id: when present, the desktop client knows the latest
    # user turn is still in-flight and shouldn't render as "Worked for X".
    sid = data.state.session_id
    active_run = runtime.run_registry.get_active_run(sid) if runtime.run_registry else None
    active_run_id = active_run.run_id if active_run else None

    # Tools carry a `kind` ("tool" | "agent") that the desktop renderer uses
    # to pick a row surface. We thread it into the history payload so a
    # reloaded session keeps the same UI as the live stream.
    def _kind_for(name: str) -> str:
        if not runtime.executor:
            return "tool"
        tool = runtime.executor.registry.get(name)
        return getattr(tool, "kind", "tool") if tool else "tool"

    history = []
    for msg in data.messages:
        role = msg["role"]
        if role == Role.SYSTEM:
            continue

        raw_content = msg.get("content", "") or ""
        if role == Role.USER and isinstance(raw_content, list):
            text_parts = [b["text"] for b in raw_content if isinstance(b, dict) and b.get("type") == "text"]
            images = [
                {"media_type": b["media_type"], "data": b["data"]}
                for b in raw_content
                if isinstance(b, dict) and b.get("type") == "image"
            ]
            context = [
                {k: v for k, v in b.items() if k != "type" and v is not None}
                for b in raw_content
                if isinstance(b, dict) and b.get("type") == "context"
            ]
            entry: dict = {"role": role, "content": "\n\n".join(text_parts)}
            if images:
                entry["images"] = images
            if context:
                entry["context"] = context
        else:
            entry = {"role": role, "content": blocks_to_text(raw_content)}

        if role == Role.ASSISTANT and "tool_calls" in msg:
            entry["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"].get("arguments", "{}"),
                    "kind": _kind_for(tc["function"]["name"]),
                }
                for tc in msg["tool_calls"]
            ]
        if role == Role.ASSISTANT and msg.get("reasoning_content"):
            entry["reasoning_content"] = msg["reasoning_content"]

        if role == Role.TOOL and "tool_call_id" in msg:
            entry["tool_call_id"] = msg["tool_call_id"]

        # Stable client-side id (the same one we streamed in SSE for assistant
        # turns). Lets the desktop client key React components and reference
        # the message in branch / edit calls without positional games.
        if msg.get("client_id"):
            entry["id"] = msg["client_id"]

        if created_at := msg.get("created_at"):
            entry["created_at"] = created_at

        history.append(entry)

    return {"messages": history[-HISTORY_MESSAGE_LIMIT:], "active_run_id": active_run_id}


@router.get("/session")
async def get_session(
    runtime: Runtime = Depends(get_runtime),
    svc: SessionService = Depends(require_session_service),
    session_id: str | None = None,
) -> SessionResponse:
    data = await svc.load(session_id)
    if data:
        session_state = data.state
    else:
        session_state = svc.create()

    return SessionResponse(
        session_id=session_state.session_id,
        integrations=runtime.get_available_integrations(),
        integration_errors=runtime.get_integration_errors(),
        name=session_state.name,
    )


@router.post("/session/clear")
async def clear_session(svc: SessionService = Depends(require_session_service), req: ClearSessionRequest | None = None):
    target_id = req.session_id if req else None

    data = await svc.load(target_id)
    if not data:
        return {"status": "cleared", "session_id": None}

    data.state.last_activity = data.state.started_at
    await svc.save(data.state, [])

    return {
        "status": "cleared",
        "session_id": data.state.session_id,
    }


@router.post("/session/revert")
async def revert_session(svc: SessionService = Depends(require_session_service), req: RevertRequest | None = None):
    target_id = req.session_id if req else None
    turns = req.turns if req else 1
    message_id = req.message_id if req else None
    result = await svc.revert(target_id, turns=turns, message_id=message_id)
    if not result:
        raise HTTPException(status_code=400, detail="Nothing to revert")
    return result


# --- Multi-session ---


@router.post("/sessions/{session_id}/branch")
async def branch_session(
    session_id: str,
    req: BranchRequest | None = None,
    svc: SessionService = Depends(require_session_service),
):
    name = req.name if req else None
    up_to_id = req.up_to_message_id if req else None
    from_end = req.from_end_index if req else None
    state = await svc.branch(
        session_id,
        name=name,
        up_to_message_id=up_to_id,
        from_end_index=from_end,
    )
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": state.session_id,
        "name": state.name,
        "started_at": state.started_at.isoformat(),
        "last_activity": state.last_activity.isoformat(),
    }


@router.post("/sessions")
async def create_session(
    svc: SessionService = Depends(require_session_service), req: CreateSessionRequest | None = None
):
    name = req.name if req else None
    state = svc.create(name=name)
    await svc.save(state, [])
    return {
        "session_id": state.session_id,
        "name": state.name,
        "started_at": state.started_at.isoformat(),
        "last_activity": state.last_activity.isoformat(),
        "message_count": 0,
    }


@router.get("/sessions")
async def list_sessions(svc: SessionService = Depends(require_session_service)):
    sessions = await svc.list_sessions(limit=20)
    return {"sessions": sessions}


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str, req: RenameSessionRequest, svc: SessionService = Depends(require_session_service)
):
    updated = await svc.rename(session_id, req.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "name": req.name}


@router.delete("/sessions/{session_id}")
async def archive_session(session_id: str, svc: SessionService = Depends(require_session_service)):
    archived = await svc.archive(session_id)
    if not archived:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "archived", "session_id": session_id}


@router.get("/sessions/archived")
async def list_archived_sessions(svc: SessionService = Depends(require_session_service)):
    sessions = await svc.list_archived(limit=20)
    return {"sessions": sessions}


@router.post("/sessions/{session_id}/restore")
async def restore_session(session_id: str, svc: SessionService = Depends(require_session_service)):
    restored = await svc.restore(session_id)
    if not restored:
        raise HTTPException(status_code=404, detail="Archived session not found")
    return {"status": "restored", "session_id": session_id}


@router.delete("/sessions/{session_id}/permanent")
async def permanently_delete_session(session_id: str, svc: SessionService = Depends(require_session_service)):
    deleted = await svc.permanently_delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Archived session not found")
    return {"status": "deleted", "session_id": session_id}
