from pathlib import Path

from ntrp.channel import Channel
from ntrp.config import NTRP_DIR
from ntrp.events.internal import SkillChanged
from ntrp.skills.installer import install_from_github
from ntrp.skills.registry import SkillMeta, SkillRegistry

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

SKILLS_DIRS: list[tuple[Path, str]] = [
    (BUILTIN_SKILLS_DIR, "builtin"),
    (Path.cwd() / ".skills", "project"),
    (NTRP_DIR / "skills", "global"),
]


class SkillService:
    def __init__(self, registry: SkillRegistry, channel: Channel):
        self._registry = registry
        self._channel = channel

    def list_all(self) -> list[SkillMeta]:
        return self._registry.list_all()

    def get(self, name: str) -> SkillMeta | None:
        return self._registry.get(name)

    async def install(self, source: str) -> SkillMeta | None:
        target_dir = NTRP_DIR / "skills"
        name = await install_from_github(source, target_dir)
        self._registry.reload(SKILLS_DIRS)
        self._channel.publish(SkillChanged())
        return self._registry.get(name)

    def remove(self, name: str) -> bool:
        removed = self._registry.remove(name)
        if removed:
            self._channel.publish(SkillChanged())
        return removed
