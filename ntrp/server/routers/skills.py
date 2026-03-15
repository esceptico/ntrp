from fastapi import APIRouter, Depends, HTTPException

from ntrp.server.deps import require_skill_service
from ntrp.server.schemas import InstallRequest
from ntrp.skills.service import SkillService

router = APIRouter(tags=["skills"])


@router.get("/skills")
async def list_skills(svc: SkillService = Depends(require_skill_service)):
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
async def install_skill(request: InstallRequest, svc: SkillService = Depends(require_skill_service)):
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
async def remove_skill(name: str, svc: SkillService = Depends(require_skill_service)):
    if not svc.remove(name):
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")
    return {"status": "removed", "name": name}
