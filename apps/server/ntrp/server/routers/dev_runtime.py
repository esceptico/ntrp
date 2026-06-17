from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["runtime-dev"])


class ScheduleDispatchRequest(BaseModel):
    prompt: str
    session_id: str


@router.post("/runtime/dev/schedules/{schedule_id}/dispatch")
async def dispatch_schedule(schedule_id: str, payload: ScheduleDispatchRequest, request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    dispatcher = getattr(runtime, "dispatch_session_message", None)
    if dispatcher is None:
        raise HTTPException(status_code=503, detail="Session dispatcher not available")
    run_id = await dispatcher(
        payload.session_id,
        payload.prompt,
        client_id=f"schedule:{schedule_id}",
        skip_approvals=False,
    )
    return {"schedule_id": schedule_id, "session_id": payload.session_id, "run_id": run_id}
