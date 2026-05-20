import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ntrp.automation.models import Automation
from ntrp.automation.service import AutomationService
from ntrp.events.sse import StreamResetEvent
from ntrp.notifiers.service import NotifierService
from ntrp.server.bus import BusRegistry, StreamRecord, stream_record_to_sse_string
from ntrp.server.deps import get_bus_registry, require_automation_service, require_notifier_service
from ntrp.server.middleware import SSEStreamingResponse
from ntrp.server.routers.chat import _keepalive
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.schemas import (
    CreateAutomationRequest,
    CreateNotifierRequest,
    UpdateAutomationRequest,
    UpdateNotifierRequest,
)

router = APIRouter(tags=["automations"])


def _automation_to_dict(a: Automation) -> dict:
    return {
        "task_id": a.task_id,
        "name": a.name,
        "description": a.description,
        "model": a.model,
        "triggers": [{"type": t.type, **t.params()} for t in a.triggers],
        "enabled": a.enabled,
        "created_at": a.created_at.isoformat(),
        "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
        "next_run_at": a.next_run_at.isoformat() if a.next_run_at else None,
        "last_result": a.last_result,
        "writable": a.writable,
        "running_since": a.running_since.isoformat() if a.running_since else None,
        "handler": a.handler,
        "builtin": a.builtin,
        "cooldown_minutes": a.cooldown_minutes,
        "kind": a.kind,
        "read_history": a.read_history,
    }


@router.post("/automations")
async def create_automation(
    request: CreateAutomationRequest, svc: AutomationService = Depends(require_automation_service)
):
    try:
        automation = await svc.create(
            name=request.name,
            description=request.description,
            model=request.model,
            trigger_type=request.trigger_type,
            at=request.at,
            days=request.days,
            every=request.every,
            event_type=request.event_type,
            lead_minutes=request.lead_minutes,
            idle_minutes=request.idle_minutes,
            every_n=request.every_n,
            actions=request.actions,
            object_types=request.object_types,
            statuses=request.statuses,
            scopes=request.scopes,
            writable=request.writable,
            start=request.start,
            end=request.end,
            triggers=request.triggers,
            cooldown_minutes=request.cooldown_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _automation_to_dict(automation)


@router.get("/automations")
async def list_automations(svc: AutomationService = Depends(require_automation_service)):
    automations = await svc.list_all()
    return {"automations": [_automation_to_dict(a) for a in automations]}


KEEPALIVE_INTERVAL = 5
AUTOMATION_BUS_KEY = "automation:events"


async def _automation_event_stream(bus_registry: BusRegistry, after_seq: int | None = None):
    bus = bus_registry.get_or_create(AUTOMATION_BUS_KEY)
    subscription = bus.subscribe_with_replay(after_seq=after_seq) if after_seq is not None else None
    queue = subscription.queue if subscription is not None else bus.subscribe()
    last_event_at = time.monotonic()
    try:
        if subscription is not None and subscription.replay_gap:
            newest_seq = bus.next_seq - 1
            reset_seq = min(max(after_seq + 1, bus.checkpoint_seq), newest_seq)
            reset_record = StreamRecord(
                seq=reset_seq,
                session_id=bus.session_id,
                event=StreamResetEvent(reason="replay_gap"),
            )
            yield stream_record_to_sse_string(bus.session_id, reset_record)
            last_event_at = time.monotonic()
            await asyncio.sleep(0)

        if subscription is not None:
            for record in subscription.snapshot:
                yield stream_record_to_sse_string(bus.session_id, record, replay=True)
                await asyncio.sleep(0)

        while True:
            try:
                record = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                if time.monotonic() - last_event_at >= KEEPALIVE_INTERVAL:
                    last_event_at = time.monotonic()
                    yield _keepalive(AUTOMATION_BUS_KEY, bus.next_seq - 1)
                continue

            if record is None:
                break

            last_event_at = time.monotonic()
            yield stream_record_to_sse_string(bus.session_id, record)
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        pass
    finally:
        bus.unsubscribe(queue)


@router.get("/automations/events")
async def automation_events(
    bus_registry: BusRegistry = Depends(get_bus_registry),
    after_seq: Annotated[int | None, Query(ge=0)] = None,
):
    return SSEStreamingResponse(
        _automation_event_stream(bus_registry, after_seq=after_seq),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/automations/{task_id}")
async def get_automation(task_id: str, svc: AutomationService = Depends(require_automation_service)):
    try:
        automation = await svc.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Automation not found")

    return _automation_to_dict(automation)


@router.post("/automations/{task_id}/toggle")
async def toggle_automation(task_id: str, svc: AutomationService = Depends(require_automation_service)):
    try:
        new_enabled = await svc.toggle_enabled(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"enabled": new_enabled}


@router.post("/automations/{task_id}/writable")
async def toggle_writable(task_id: str, svc: AutomationService = Depends(require_automation_service)):
    try:
        new_writable = await svc.toggle_writable(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"writable": new_writable}


@router.post("/automations/{task_id}/run")
async def run_automation(task_id: str, svc: AutomationService = Depends(require_automation_service)):
    try:
        await svc.run_now(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Automation not found")
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    return {"status": "started"}


@router.patch("/automations/{task_id}")
async def update_automation(
    task_id: str, request: UpdateAutomationRequest, svc: AutomationService = Depends(require_automation_service)
):
    try:
        automation = await svc.update(
            task_id,
            name=request.name,
            description=request.description,
            model=request.model,
            trigger_type=request.trigger_type,
            at=request.at,
            days=request.days,
            every=request.every,
            event_type=request.event_type,
            lead_minutes=request.lead_minutes,
            idle_minutes=request.idle_minutes,
            every_n=request.every_n,
            actions=request.actions,
            object_types=request.object_types,
            statuses=request.statuses,
            scopes=request.scopes,
            start=request.start,
            end=request.end,
            writable=request.writable,
            enabled=request.enabled,
            triggers=request.triggers,
            cooldown_minutes=request.cooldown_minutes,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Automation not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _automation_to_dict(automation)


@router.get("/notifiers")
async def list_notifiers(runtime: Runtime = Depends(get_runtime)):
    if not runtime.notifier_service:
        return {"notifiers": []}
    return {"notifiers": runtime.notifier_service.list_summary()}


@router.delete("/automations/{task_id}")
async def delete_automation(task_id: str, svc: AutomationService = Depends(require_automation_service)):
    try:
        disabled_children = await svc.delete(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Automation not found")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"status": "deleted", "disabled_children": disabled_children}


# --- Notifier config CRUD ---


@router.get("/notifiers/configs")
async def list_notifier_configs(svc: NotifierService = Depends(require_notifier_service)):
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
async def list_notifier_types(svc: NotifierService = Depends(require_notifier_service)):
    return {"types": svc.get_types()}


@router.post("/notifiers/configs")
async def create_notifier_config(
    request: CreateNotifierRequest, svc: NotifierService = Depends(require_notifier_service)
):
    try:
        cfg = await svc.create(request.name, request.type, request.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"name": cfg.name, "type": cfg.type, "config": cfg.config, "created_at": cfg.created_at.isoformat()}


@router.put("/notifiers/configs/{name}")
async def update_notifier_config(
    name: str, request: UpdateNotifierRequest, svc: NotifierService = Depends(require_notifier_service)
):
    try:
        cfg = await svc.update(name, request.config, new_name=request.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"name": cfg.name, "type": cfg.type, "config": cfg.config, "created_at": cfg.created_at.isoformat()}


@router.delete("/notifiers/configs/{name}")
async def delete_notifier_config(name: str, svc: NotifierService = Depends(require_notifier_service)):
    try:
        await svc.delete(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")

    return {"status": "deleted"}


@router.post("/notifiers/configs/{name}/test")
async def test_notifier(name: str, svc: NotifierService = Depends(require_notifier_service)):
    try:
        await svc.test(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notifier not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "sent"}
