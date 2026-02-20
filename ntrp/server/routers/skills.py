from fastapi import APIRouter, Depends, HTTPException

from ntrp.server.runtime import get_runtime
from ntrp.server.schemas import InstallRequest
from ntrp.skills.service import SkillService

router = APIRouter(tags=["skills"])


def _require_skill_service() -> SkillService:
    runtime = get_runtime()
    if not runtime.skill_service:
        raise HTTPException(status_code=503, detail="Skill service not available")
    return runtime.skill_service


@router.get("/skills")
async def list_skills(svc: SkillService = Depends(_require_skill_service)):
    return {
        "skills": [
            {
                "name": m.name,
                "description": m.description,
                "location": m.location,
            }
            for m in svc.list_all()
        ],
    }


@router.post("/skills/install")
async def install_skill(request: InstallRequest, svc: SkillService = Depends(_require_skill_service)):
    try:
        meta = await svc.install(request.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "name": meta.name if meta else request.source,
        "description": meta.description if meta else "",
        "status": "installed",
    }


@router.delete("/skills/{name}")
async def remove_skill(name: str, svc: SkillService = Depends(_require_skill_service)):
    if not svc.remove(name):
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")
    return {"status": "removed", "name": name}
