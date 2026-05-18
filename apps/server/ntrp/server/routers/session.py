from fastapi import APIRouter, Depends, HTTPException, Query

from ntrp.agent import Role
from ntrp.constants import HISTORY_MESSAGE_LIMIT
from ntrp.core.compactor import is_handoff_message
from ntrp.core.content import blocks_to_text
from ntrp.events.sse import GoalClearedEvent, GoalUpdatedEvent
from ntrp.server.bus import BusRegistry
from ntrp.server.deps import get_bus_registry, require_run_registry, require_session_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    BranchRequest,
    ClearSessionRequest,
    CreateSessionRequest,
    RenameSessionRequest,
    RevertRequest,
    SessionGoalResponse,
    SessionResponse,
    SetSessionAutoRequest,
    SetSessionGoalRequest,
    UpdateSessionGoalRequest,
)
from ntrp.server.state import RunRegistry
from ntrp.services.session import SessionService

router = APIRouter(tags=["session"])


async def _emit_goal_event(buses: BusRegistry, session_id: str, goal: dict | None) -> None:
    bus = buses.get_or_create(session_id)
    if goal is None:
        await bus.emit(GoalClearedEvent(session_id=session_id))
    else:
        await bus.emit(GoalUpdatedEvent(session_id=session_id, goal=goal))


@router.get("/session/history")
async def get_session_history(
    svc: SessionService = Depends(require_session_service),
    runtime: Runtime = Depends(get_runtime),
    session_id: str | None = None,
    limit: int = Query(default=HISTORY_MESSAGE_LIMIT, ge=1, le=250),
    before: str | None = None,
    after: str | None = None,
    around: str | None = None,
    around_seq: int | None = Query(default=None, ge=0),
):
    data = await svc.load(session_id)
    if not data:
        return {"messages": [], "active_run_id": None, "page": {"has_more_before": False, "has_more_after": False}}

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

    page = await svc.list_messages(
        sid,
        limit=limit,
        before=before,
        after=after,
        around=around,
        around_seq=around_seq,
    )

    history = []
    for row in page["messages"]:
        msg = row["message"]
        role = msg["role"]
        if role == Role.SYSTEM:
            continue
        if is_handoff_message(msg):
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
        elif row.get("message_id"):
            entry["id"] = row["message_id"]

        entry["message_id"] = row["message_id"]
        entry["seq"] = row["seq"]

        if created_at := msg.get("created_at"):
            entry["created_at"] = created_at

        # Loop-fired user messages are visible to the model (kept in history
        # so the agent can act on them) but hidden from the transcript UI.
        if msg.get("is_meta"):
            entry["is_meta"] = True

        history.append(entry)

    return {
        "messages": history,
        "active_run_id": active_run_id,
        "page": {
            "has_more_before": page["has_more_before"],
            "has_more_after": page["has_more_after"],
            "before": page["before"],
            "after": page["after"],
        },
        # Snapshot of the session's budget-relevant counters so the desktop
        # can populate the BudgetDial immediately on session open instead of
        # waiting for the next run to finish and emit RunFinishedEvent.
        # `last_message_count` reflects durable transcript pressure. Falls
        # back to the on-disk count for sessions saved before this field
        # existed.
        "usage": {
            "last_input_tokens": data.last_input_tokens or 0,
            "message_count": data.last_message_count
            if data.last_message_count is not None
            else len(data.messages),
        },
    }


@router.get("/session/episodes")
async def get_session_episodes(
    svc: SessionService = Depends(require_session_service),
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    data = await svc.load(session_id)
    if not data:
        return {"episodes": []}
    return {"episodes": await svc.list_episodes(data.state.session_id, limit=limit)}


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


@router.get("/sessions/{session_id}/goal", response_model=SessionGoalResponse | None)
async def get_session_goal(
    session_id: str,
    svc: SessionService = Depends(require_session_service),
):
    return await svc.get_goal(session_id)


@router.post("/sessions/{session_id}/goal", response_model=SessionGoalResponse)
async def set_session_goal(
    session_id: str,
    req: SetSessionGoalRequest,
    svc: SessionService = Depends(require_session_service),
    buses: BusRegistry = Depends(get_bus_registry),
):
    if not await svc.load(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    objective = req.objective.strip()
    if not objective:
        raise HTTPException(status_code=422, detail="Goal objective cannot be blank")
    goal = await svc.set_goal(session_id, objective, token_budget=req.token_budget)
    if not goal:
        raise HTTPException(status_code=500, detail="Failed to set goal")
    await _emit_goal_event(buses, session_id, goal)
    return goal


@router.patch("/sessions/{session_id}/goal", response_model=SessionGoalResponse)
async def update_session_goal(
    session_id: str,
    req: UpdateSessionGoalRequest,
    svc: SessionService = Depends(require_session_service),
    buses: BusRegistry = Depends(get_bus_registry),
):
    blocked_reason = req.blocked_reason.strip() if req.blocked_reason else None
    if req.status == "blocked" and not blocked_reason:
        raise HTTPException(status_code=422, detail="blocked_reason is required when blocking a goal")
    goal = await svc.update_goal(
        session_id,
        status=req.status,
        evidence=req.evidence.strip() if req.evidence else None,
        blocked_reason=blocked_reason,
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    await _emit_goal_event(buses, session_id, goal)
    return goal


@router.delete("/sessions/{session_id}/goal")
async def clear_session_goal(
    session_id: str,
    svc: SessionService = Depends(require_session_service),
    buses: BusRegistry = Depends(get_bus_registry),
):
    cleared = await svc.clear_goal(session_id)
    if cleared:
        await _emit_goal_event(buses, session_id, None)
    return {"status": "cleared", "session_id": session_id}


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


@router.post("/sessions/{session_id}/auto")
async def set_session_auto(
    session_id: str,
    req: SetSessionAutoRequest,
    run_registry: RunRegistry = Depends(require_run_registry),
):
    """Apply an Auto-mode toggle to the live session.

    When `value=True`: future tool calls in the active run skip approval, and
    any approval Futures currently awaiting user input resolve as approved.
    When `value=False`: just flips the flag; pending approvals stay pending.
    """
    active = run_registry.get_accepting_run(session_id)
    resolved = 0
    if active is not None:
        if active.session_state is not None:
            active.session_state.skip_approvals = req.value
        if req.value:
            for tool_id, future in list(active.pending_approvals.items()):
                if future.done():
                    continue
                future.set_result({
                    "type": "tool_response",
                    "tool_id": tool_id,
                    "result": "",
                    "approved": True,
                })
                resolved += 1
    return {"status": "ok", "skip_approvals": req.value, "auto_resolved": resolved}


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
