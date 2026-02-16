import asyncio

from fastapi import APIRouter, HTTPException

from ntrp.server.runtime import get_runtime
from ntrp.server.schemas import (
    CreateNotifierRequest,
    SetNotifiersRequest,
    UpdateNotifierRequest,
    UpdateScheduleRequest,
)

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
                "name": t.name,
                "description": t.description,
                "time_of_day": t.time_of_day,
                "recurrence": t.recurrence.value,
                "enabled": t.enabled,
                "created_at": t.created_at.isoformat(),
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
                "notifiers": t.notifiers,
                "writable": t.writable,
                "running_since": t.running_since.isoformat() if t.running_since else None,
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
        "name": task.name,
        "description": task.description,
        "time_of_day": task.time_of_day,
        "recurrence": task.recurrence.value,
        "enabled": task.enabled,
        "created_at": task.created_at.isoformat(),
        "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        "notifiers": task.notifiers,
        "last_result": task.last_result,
        "writable": task.writable,
        "running_since": task.running_since.isoformat() if task.running_since else None,
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


@router.post("/schedules/{task_id}/writable")
async def toggle_writable(task_id: str):
    runtime = get_runtime()
    if not runtime.schedule_store:
        raise HTTPException(status_code=503, detail="Scheduling not available")

    task = await runtime.schedule_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_writable = not task.writable
    await runtime.schedule_store.set_writable(task_id, new_writable)
    return {"writable": new_writable}


@router.post("/schedules/{task_id}/run")
async def run_schedule(task_id: str):
    runtime = get_runtime()
    if not runtime.scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    task = await runtime.schedule_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.running_since:
        raise HTTPException(status_code=409, detail="Task is already running")

    asyncio.create_task(runtime.scheduler.run_now(task_id))
    return {"status": "started"}


@router.patch("/schedules/{task_id}")
async def update_schedule(task_id: str, request: UpdateScheduleRequest):
    runtime = get_runtime()
    if not runtime.schedule_store:
        raise HTTPException(status_code=503, detail="Scheduling not available")

    task = await runtime.schedule_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if request.name is not None:
        await runtime.schedule_store.update_name(task_id, request.name)
    if request.description is not None:
        await runtime.schedule_store.update_description(task_id, request.description)
    return {"name": request.name or task.name, "description": request.description or task.description}


@router.get("/notifiers")
async def list_notifiers():
    runtime = get_runtime()
    return {"notifiers": list(runtime.notifiers.keys())}


@router.put("/schedules/{task_id}/notifiers")
async def set_notifiers(task_id: str, request: SetNotifiersRequest):
    runtime = get_runtime()
    if not runtime.schedule_store:
        raise HTTPException(status_code=503, detail="Scheduling not available")

    task = await runtime.schedule_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for name in request.notifiers:
        if name not in runtime.notifiers:
            raise HTTPException(status_code=400, detail=f"Unknown notifier: {name}")

    await runtime.schedule_store.set_notifiers(task_id, request.notifiers)
    return {"notifiers": request.notifiers}


@router.delete("/schedules/{task_id}")
async def delete_schedule(task_id: str):
    runtime = get_runtime()
    if not runtime.schedule_store:
        raise HTTPException(status_code=503, detail="Scheduling not available")

    deleted = await runtime.schedule_store.delete(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted"}


# --- Notifier config CRUD ---


@router.get("/notifiers/configs")
async def list_notifier_configs():
    runtime = get_runtime()
    if not runtime.notifier_store:
        return {"configs": []}

    configs = await runtime.notifier_store.list_all()
    return {
        "configs": [
            {
                "name": c.name,
                "type": c.type,
                "config": c.config,
                "created_at": c.created_at.isoformat(),
            }
            for c in configs
        ]
    }


@router.get("/notifiers/types")
async def list_notifier_types():
    runtime = get_runtime()
    gmail = runtime.get_gmail()
    accounts = gmail.list_accounts() if gmail else []

    return {
        "types": {
            "email": {"fields": ["from_account", "to_address"], "accounts": accounts},
            "telegram": {"fields": ["user_id"]},
            "bash": {"fields": ["command"]},
        }
    }


@router.post("/notifiers/configs")
async def create_notifier_config(request: CreateNotifierRequest):
    runtime = get_runtime()
    if not runtime.notifier_service:
        raise HTTPException(status_code=503, detail="Notifier store not available")

    try:
        cfg = await runtime.notifier_service.create(request.name, request.type, request.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"name": cfg.name, "type": cfg.type, "config": cfg.config, "created_at": cfg.created_at.isoformat()}


@router.put("/notifiers/configs/{name}")
async def update_notifier_config(name: str, request: UpdateNotifierRequest):
    runtime = get_runtime()
    if not runtime.notifier_service:
        raise HTTPException(status_code=503, detail="Notifier store not available")

    try:
        cfg = await runtime.notifier_service.update(name, request.config, new_name=request.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"name": cfg.name, "type": cfg.type, "config": cfg.config, "created_at": cfg.created_at.isoformat()}


@router.delete("/notifiers/configs/{name}")
async def delete_notifier_config(name: str):
    runtime = get_runtime()
    if not runtime.notifier_service:
        raise HTTPException(status_code=503, detail="Notifier store not available")

    try:
        await runtime.notifier_service.delete(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")

    return {"status": "deleted"}


@router.post("/notifiers/configs/{name}/test")
async def test_notifier(name: str):
    runtime = get_runtime()
    if not runtime.notifier_service:
        raise HTTPException(status_code=503, detail="Notifier service not available")

    try:
        await runtime.notifier_service.test(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "sent"}
