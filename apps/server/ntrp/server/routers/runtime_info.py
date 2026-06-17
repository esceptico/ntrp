from pathlib import Path

from fastapi import APIRouter

from ntrp.agent_surface.models import RuntimeInfo
from ntrp.agent_surface.runtime_info import build_runtime_info

router = APIRouter(tags=["runtime"])


@router.get("/runtime/info", response_model=RuntimeInfo)
async def runtime_info():
    return build_runtime_info(Path.cwd())
