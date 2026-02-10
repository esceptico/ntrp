import asyncio
import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ntrp.notifiers.models import NotifierConfig
from ntrp.server.runtime import get_runtime

router = APIRouter(tags=["schedule"])


class UpdateScheduleRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class SetNotifiersRequest(BaseModel):
    notifiers: list[str]


class CreateNotifierRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str
    config: dict


class UpdateNotifierRequest(BaseModel):
    config: dict


VALID_TYPES = {"email", "telegram", "bash"}
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")


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


def _validate_notifier_config(notifier_type: str, config: dict) -> None:
    if notifier_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid notifier type: {notifier_type}")

    if notifier_type == "email":
        if not config.get("from_account"):
            raise HTTPException(status_code=400, detail="from_account is required")
        if not config.get("to_address"):
            raise HTTPException(status_code=400, detail="to_address is required")
        gmail = get_runtime().get_gmail()
        if gmail:
            accounts = gmail.list_accounts()
            if config["from_account"] not in accounts:
                raise HTTPException(status_code=400, detail=f"Unknown Gmail account: {config['from_account']}")
    elif notifier_type == "telegram":
        if not config.get("user_id"):
            raise HTTPException(status_code=400, detail="user_id is required")
    elif notifier_type == "bash":
        if not config.get("command"):
            raise HTTPException(status_code=400, detail="command is required")


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
    if not runtime.notifier_store:
        raise HTTPException(status_code=503, detail="Notifier store not available")

    if not NAME_RE.match(request.name):
        raise HTTPException(status_code=400, detail="Name must be alphanumeric with hyphens")

    existing = await runtime.notifier_store.get(request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Notifier '{request.name}' already exists")

    _validate_notifier_config(request.type, request.config)

    cfg = NotifierConfig(
        name=request.name,
        type=request.type,
        config=request.config,
        created_at=datetime.now(UTC),
    )
    await runtime.notifier_store.save(cfg)
    await runtime.rebuild_notifiers()

    return {"name": cfg.name, "type": cfg.type, "config": cfg.config, "created_at": cfg.created_at.isoformat()}


@router.put("/notifiers/configs/{name}")
async def update_notifier_config(name: str, request: UpdateNotifierRequest):
    runtime = get_runtime()
    if not runtime.notifier_store:
        raise HTTPException(status_code=503, detail="Notifier store not available")

    existing = await runtime.notifier_store.get(name)
    if not existing:
        raise HTTPException(status_code=404, detail="Notifier not found")

    _validate_notifier_config(existing.type, request.config)

    existing.config = request.config
    await runtime.notifier_store.save(existing)
    await runtime.rebuild_notifiers()

    return {"name": existing.name, "type": existing.type, "config": existing.config, "created_at": existing.created_at.isoformat()}


@router.delete("/notifiers/configs/{name}")
async def delete_notifier_config(name: str):
    runtime = get_runtime()
    if not runtime.notifier_store:
        raise HTTPException(status_code=503, detail="Notifier store not available")

    deleted = await runtime.notifier_store.delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notifier not found")

    # Remove from any schedules that reference this notifier
    if runtime.schedule_store:
        tasks = await runtime.schedule_store.list_all()
        for task in tasks:
            if name in task.notifiers:
                new_notifiers = [n for n in task.notifiers if n != name]
                await runtime.schedule_store.set_notifiers(task.task_id, new_notifiers)

    await runtime.rebuild_notifiers()
    return {"status": "deleted"}


@router.post("/notifiers/configs/{name}/test")
async def test_notifier(name: str):
    runtime = get_runtime()
    notifier = runtime.notifiers.get(name)
    if not notifier:
        raise HTTPException(status_code=404, detail="Notifier not found")

    try:
        await notifier.send("Hello from ntrp", "Test notification — if you see this, it works!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "sent"}
