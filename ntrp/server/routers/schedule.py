from fastapi import APIRouter, HTTPException

from ntrp.server.runtime import get_runtime

router = APIRouter(tags=["schedule"])


@router.get("/schedules")
async def list_schedules():
    runtime = get_runtime()
    if not runtime.schedule_store:
        return {"schedules": []}

    tasks = await runtime.schedule_store.list_all()
    return {
        "schedules": [
            {
                "task_id": t.task_id,
                "description": t.description,
                "time_of_day": t.time_of_day,
                "recurrence": t.recurrence.value,
                "enabled": t.enabled,
                "created_at": t.created_at.isoformat(),
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
                "notify_email": t.notify_email,
            }
            for t in tasks
        ]
    }


@router.get("/schedules/{task_id}")
async def get_schedule(task_id: str):
    runtime = get_runtime()
    if not runtime.schedule_store:
        raise HTTPException(status_code=503, detail="Scheduling not available")

    task = await runtime.schedule_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task.task_id,
        "description": task.description,
        "time_of_day": task.time_of_day,
        "recurrence": task.recurrence.value,
        "enabled": task.enabled,
        "created_at": task.created_at.isoformat(),
        "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        "notify_email": task.notify_email,
        "last_result": task.last_result,
    }


@router.post("/schedules/{task_id}/toggle")
async def toggle_schedule(task_id: str):
    runtime = get_runtime()
    if not runtime.schedule_store:
        raise HTTPException(status_code=503, detail="Scheduling not available")

    task = await runtime.schedule_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_enabled = not task.enabled
    await runtime.schedule_store.set_enabled(task_id, new_enabled)
    return {"enabled": new_enabled}


@router.delete("/schedules/{task_id}")
async def delete_schedule(task_id: str):
    runtime = get_runtime()
    if not runtime.schedule_store:
        raise HTTPException(status_code=503, detail="Scheduling not available")

    deleted = await runtime.schedule_store.delete(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted"}
