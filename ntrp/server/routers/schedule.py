from fastapi import APIRouter, Depends, HTTPException

from ntrp.notifiers.service import NotifierService
from ntrp.schedule.service import ScheduleService
from ntrp.server.runtime import get_runtime
from ntrp.server.schemas import (
    CreateNotifierRequest,
    SetNotifiersRequest,
    UpdateNotifierRequest,
    UpdateScheduleRequest,
)

router = APIRouter(tags=["schedule"])


def _require_schedule_service() -> ScheduleService:
    runtime = get_runtime()
    if not runtime.schedule_service:
        raise HTTPException(status_code=503, detail="Scheduling not available")
    return runtime.schedule_service


def _require_notifier_service() -> NotifierService:
    runtime = get_runtime()
    if not runtime.notifier_service:
        raise HTTPException(status_code=503, detail="Notifier service not available")
    return runtime.notifier_service


@router.get("/schedules")
async def list_schedules():
    runtime = get_runtime()
    if not runtime.schedule_service:
        return {"schedules": []}

    tasks = await runtime.schedule_service.list_all()
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
async def get_schedule(task_id: str, svc: ScheduleService = Depends(_require_schedule_service)):
    try:
        task = await svc.get(task_id)
    except KeyError:
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
async def toggle_schedule(task_id: str, svc: ScheduleService = Depends(_require_schedule_service)):
    try:
        new_enabled = await svc.toggle_enabled(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"enabled": new_enabled}


@router.post("/schedules/{task_id}/writable")
async def toggle_writable(task_id: str, svc: ScheduleService = Depends(_require_schedule_service)):
    try:
        new_writable = await svc.toggle_writable(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"writable": new_writable}


@router.post("/schedules/{task_id}/run")
async def run_schedule(task_id: str, svc: ScheduleService = Depends(_require_schedule_service)):
    try:
        await svc.run_now(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "started"}


@router.patch("/schedules/{task_id}")
async def update_schedule(
    task_id: str, request: UpdateScheduleRequest, svc: ScheduleService = Depends(_require_schedule_service)
):
    try:
        task = await svc.update(task_id, name=request.name, description=request.description)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"name": task.name, "description": task.description}


@router.get("/notifiers")
async def list_notifiers():
    runtime = get_runtime()
    if not runtime.notifier_service:
        return {"notifiers": []}
    return {"notifiers": runtime.notifier_service.list_summary()}


@router.put("/schedules/{task_id}/notifiers")
async def set_notifiers(
    task_id: str, request: SetNotifiersRequest, svc: ScheduleService = Depends(_require_schedule_service)
):
    try:
        await svc.set_notifiers(task_id, request.notifiers)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"notifiers": request.notifiers}


@router.delete("/schedules/{task_id}")
async def delete_schedule(task_id: str, svc: ScheduleService = Depends(_require_schedule_service)):
    try:
        await svc.delete(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted"}


# --- Notifier config CRUD ---


@router.get("/notifiers/configs")
async def list_notifier_configs(svc: NotifierService = Depends(_require_notifier_service)):
    configs = await svc.list_configs()
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
async def list_notifier_types(svc: NotifierService = Depends(_require_notifier_service)):
    return {"types": svc.get_types()}


@router.post("/notifiers/configs")
async def create_notifier_config(
    request: CreateNotifierRequest, svc: NotifierService = Depends(_require_notifier_service)
):
    try:
        cfg = await svc.create(request.name, request.type, request.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"name": cfg.name, "type": cfg.type, "config": cfg.config, "created_at": cfg.created_at.isoformat()}


@router.put("/notifiers/configs/{name}")
async def update_notifier_config(
    name: str, request: UpdateNotifierRequest, svc: NotifierService = Depends(_require_notifier_service)
):
    try:
        cfg = await svc.update(name, request.config, new_name=request.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"name": cfg.name, "type": cfg.type, "config": cfg.config, "created_at": cfg.created_at.isoformat()}


@router.delete("/notifiers/configs/{name}")
async def delete_notifier_config(name: str, svc: NotifierService = Depends(_require_notifier_service)):
    try:
        await svc.delete(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")

    return {"status": "deleted"}


@router.post("/notifiers/configs/{name}/test")
async def test_notifier(name: str, svc: NotifierService = Depends(_require_notifier_service)):
    try:
        await svc.test(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "sent"}
