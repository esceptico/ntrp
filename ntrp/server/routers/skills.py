from fastapi import APIRouter, HTTPException

from ntrp.server.runtime import get_runtime
from ntrp.server.schemas import InstallRequest

router = APIRouter(tags=["skills"])


@router.get("/skills")
async def list_skills():
    runtime = get_runtime()
    return {
        "skills": [
            {
                "name": m.name,
                "description": m.description,
                "location": m.location,
            }
            for m in runtime.skill_service.list_all()
        ],
    }


@router.post("/skills/install")
async def install_skill(request: InstallRequest):
    runtime = get_runtime()

    try:
        meta = await runtime.skill_service.install(request.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "name": meta.name if meta else request.source,
        "description": meta.description if meta else "",
        "status": "installed",
    }


@router.delete("/skills/{name}")
async def remove_skill(name: str):
    runtime = get_runtime()
    if not runtime.skill_service.remove(name):
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")
    return {"status": "removed", "name": name}
