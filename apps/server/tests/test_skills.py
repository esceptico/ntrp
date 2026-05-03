from ntrp.skills.registry import SkillRegistry
from ntrp.skills.service import get_skills_dirs


def test_builtin_obsidian_skill_is_registered():
    registry = SkillRegistry()
    registry.load(get_skills_dirs())

    skill = registry.get("obsidian")

    assert skill is not None
    assert skill.location == "builtin"
