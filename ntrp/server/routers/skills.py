from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ntrp.config import NTRP_DIR
from ntrp.server.runtime import get_runtime
from ntrp.skills.installer import install_from_github

router = APIRouter(tags=["skills"])

_SKILLS_DIRS = [
    (Path.cwd() / ".skills", "project"),
    (NTRP_DIR / "skills", "global"),
]


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
            for m in runtime.skill_registry._skills.values()
        ],
    }


class InstallRequest(BaseModel):
    source: str = Field(..., min_length=5, description="GitHub path: owner/repo/path/to/skill")


@router.post("/skills/install")
async def install_skill(request: InstallRequest):
    runtime = get_runtime()
    target_dir = NTRP_DIR / "skills"

    try:
        name = await install_from_github(request.source, target_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    runtime.skill_registry.reload(_SKILLS_DIRS)
    runtime.rebuild_executor()

    meta = runtime.skill_registry.get(name)
    return {
        "name": name,
        "description": meta.description if meta else "",
        "status": "installed",
    }


@router.delete("/skills/{name}")
async def remove_skill(name: str):
    runtime = get_runtime()
    if not runtime.skill_registry.remove(name):
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")
    runtime.rebuild_executor()
    return {"status": "removed", "name": name}
