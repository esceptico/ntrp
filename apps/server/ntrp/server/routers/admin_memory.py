from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ntrp.memory.pattern_finder import PatternFinder
from ntrp.server.deps import require_pattern_finder

router = APIRouter(prefix="/admin/memory", tags=["admin"])


class PatternFinderRunRequest(BaseModel):
    window_days: int = Field(default=7, ge=1, le=90)
    scope: str = "user"
    limit: int = Field(default=500, ge=1, le=1000)


@router.post("/pattern-finder/run")
async def run_pattern_finder(
    request: PatternFinderRunRequest,
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    result = await pattern_finder.run_pass1(
        window_days=request.window_days,
        scope=request.scope,
        limit=request.limit,
    )
    return result.to_dict()
