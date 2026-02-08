from fastapi import APIRouter

from ntrp.server.runtime import get_runtime

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/overview")
async def get_dashboard_overview():
    runtime = get_runtime()
    return await runtime.dashboard.snapshot_async(runtime)
