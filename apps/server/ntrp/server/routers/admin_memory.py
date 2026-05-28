from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ntrp.memory.pattern_finder import PatternFinder
from ntrp.server.deps import require_pattern_finder

router = APIRouter(prefix="/admin/memory", tags=["admin"])


class PatternFinderRunRequest(BaseModel):
    pass_: int | str | None = Field(default=None, alias="pass")
    window_days: int | None = Field(default=None, ge=1, le=90)
    scope: str = "user"
    limit: int = Field(default=500, ge=1, le=1000)


@router.post("/pattern-finder/run")
async def run_pattern_finder(
    request: PatternFinderRunRequest,
    pattern_finder: PatternFinder = Depends(require_pattern_finder),
):
    selected_pass = request.pass_
    if selected_pass is None:
        result = await pattern_finder.run_pass1(
            window_days=request.window_days or 7,
            scope=request.scope,
            limit=request.limit,
        )
        return result.to_dict()
    if selected_pass in {1, "1"}:
        result = await pattern_finder.run_pass1(
            window_days=request.window_days or 7,
            scope=request.scope,
            limit=request.limit,
        )
        return {"pass1": result.to_dict()}
    if selected_pass in {2, "2"}:
        result = await pattern_finder.run_pass2(
            window_days=request.window_days or 30,
            scope=request.scope,
            limit=request.limit,
        )
        return {"pass2": result.to_dict()}
    if selected_pass == "both":
        pass1 = await pattern_finder.run_pass1(
            window_days=request.window_days or 7,
            scope=request.scope,
            limit=request.limit,
        )
        pass2 = await pattern_finder.run_pass2(
            window_days=request.window_days or 30,
            scope=request.scope,
            limit=request.limit,
        )
        return {"pass1": pass1.to_dict(), "pass2": pass2.to_dict()}
    raise HTTPException(status_code=400, detail="pass must be 1, 2, or 'both'")
