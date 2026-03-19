from fastapi import APIRouter, Depends, HTTPException

from ntrp.constants import HISTORY_MESSAGE_LIMIT
from ntrp.llm.utils import blocks_to_text
from ntrp.server.deps import require_session_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    ClearSessionRequest,
    CreateSessionRequest,
    RenameSessionRequest,
    RevertRequest,
    SessionResponse,
)
from ntrp.services.session import SessionService

router = APIRouter(tags=["session"])


@router.get("/session/history")
async def get_session_history(svc: SessionService = Depends(require_session_service), session_id: str | None = None):
    data = await svc.load(session_id)
    if not data:
        return {"messages": []}

    history = []
    for msg in data.messages:
        role = msg["role"]
        if role == "system":
            continue

        raw_content = msg.get("content", "") or ""
        if role == "user" and isinstance(raw_content, list):
            text_parts = [b["text"] for b in raw_content if isinstance(b, dict) and b.get("type") == "text"]
            images = [
                {"media_type": b["media_type"], "data": b["data"]}
                for b in raw_content
                if isinstance(b, dict) and b.get("type") == "image"
            ]
            entry: dict = {"role": role, "content": "\n\n".join(text_parts)}
            if images:
                entry["images"] = images
        else:
            entry = {"role": role, "content": blocks_to_text(raw_content)}

        if role == "assistant" and "tool_calls" in msg:
            entry["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"].get("arguments", "{}"),
                }
                for tc in msg["tool_calls"]
            ]

        if role == "tool" and "tool_call_id" in msg:
            entry["tool_call_id"] = msg["tool_call_id"]

        history.append(entry)

    return {"messages": history[-HISTORY_MESSAGE_LIMIT:]}


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
        sources=runtime.get_available_sources(),
        source_errors=runtime.get_source_errors(),
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
    result = await svc.revert(target_id, turns=turns)
    if not result:
        raise HTTPException(status_code=400, detail="Nothing to revert")
    return result


# --- Multi-session ---


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
