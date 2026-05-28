import re
from datetime import date
from pathlib import Path

from ntrp.settings import NTRP_DIR
from ntrp.skills.installer import install_from_github
from ntrp.skills.registry import SkillMeta, SkillRegistry

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

# Skill names: lowercase letters, digits, hyphens. Must start with a letter.
# Matches the convention used across builtin skills and the propose-skill
# instructions.
_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,47}$")


def get_skills_dirs() -> list[tuple[Path, str]]:
    return [
        (BUILTIN_SKILLS_DIR, "builtin"),
        (Path.cwd() / ".skills", "project"),
        (NTRP_DIR / "skills", "global"),
    ]


class SkillService:
    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def list_all(self) -> list[SkillMeta]:
        return self._registry.list_all()

    def get(self, name: str) -> SkillMeta | None:
        return self._registry.get(name)

    def governance_report(self, *, now_date: str | None = None) -> dict:
        today = date.fromisoformat(now_date) if now_date else date.today()
        inventory = []
        cleanup_candidates = []

        for skill in self._registry.list_all():
            row = {
                "name": skill.name,
                "description": skill.description,
                "location": skill.location,
                "path": str(skill.path),
                "source": skill.source,
                "version": skill.version,
                "reviewed_at": skill.reviewed_at,
            }
            inventory.append(row)
            if skill.reviewed_at:
                reviewed = date.fromisoformat(skill.reviewed_at)
                if (today - reviewed).days >= 180:
                    cleanup_candidates.append({**row, "reason": "review_stale"})

        return {
            "summary": {
                "skill_count": len(inventory),
                "validation_issue_count": len(self._registry.validation_issues),
                "cleanup_candidate_count": len(cleanup_candidates),
            },
            "inventory": inventory,
            "validation_issues": self._registry.validation_issues,
            "cleanup_candidates": cleanup_candidates,
        }

    async def install(self, source: str) -> SkillMeta | None:
        target_dir = NTRP_DIR / "skills"
        name = await install_from_github(source, target_dir)
        self._registry.reload(get_skills_dirs())
        return self._registry.get(name)

    def create(self, name: str, description: str, body: str, *, source: str | None = None) -> SkillMeta:
        """Write a new global skill (~/.ntrp/skills/<name>/SKILL.md) from
        inline content. Used by the propose-skill flow when the user accepts
        a proposal card. Raises ValueError on invalid input or name conflict.
        """
        if not _SKILL_NAME_RE.fullmatch(name):
            raise ValueError(
                "Skill name must be lowercase letters/digits/hyphens, "
                "start with a letter, max 48 chars."
            )
        if not description.strip():
            raise ValueError("Skill description is required.")
        if not body.strip():
            raise ValueError("Skill body is required.")
        if self._registry.get(name) is not None:
            raise ValueError(f"Skill '{name}' already exists.")

        target_dir = NTRP_DIR / "skills" / name
        target_dir.mkdir(parents=True, exist_ok=False)
        skill_md = target_dir / "SKILL.md"
        # Strip a stray leading/trailing newline so the file's shape stays
        # consistent regardless of how the model formatted its JSON value.
        normalized_body = body.strip()
        source_value = source.strip().replace("\r", " ").replace("\n", " ") if source else ""
        source_line = f"source: {source_value}\n" if source_value else ""
        content = (
            "---\n"
            f"name: {name}\n"
            f"description: {description.strip()}\n"
            f"{source_line}"
            "---\n\n"
            f"{normalized_body}\n"
        )
        skill_md.write_text(content)

        self._registry.reload(get_skills_dirs())
        meta = self._registry.get(name)
        if meta is None:
            # Shouldn't happen — we just wrote the file. Surface clearly.
            raise RuntimeError(f"Failed to load created skill '{name}'.")
        return meta

    def remove(self, name: str) -> bool:
        return self._registry.remove(name)
