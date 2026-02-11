import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ntrp.logging import get_logger

_logger = get_logger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class SkillMeta:
    name: str
    description: str
    path: Path
    location: str


def _parse_skill_md(content: str) -> tuple[dict, str] | None:
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    try:
        frontmatter = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict):
        return None
    return frontmatter, content[m.end():]


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, SkillMeta] = {}

    def load(self, dirs: list[tuple[Path, str]]) -> None:
        for path, location in dirs:
            self._scan_dir(path, location)
        if self._skills:
            _logger.info("Loaded %d skill(s): %s", len(self._skills), ", ".join(self._skills))

    def _scan_dir(self, base: Path, location: str) -> None:
        if not base.exists():
            return
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                content = skill_md.read_text()
            except OSError:
                _logger.warning("Failed to read %s", skill_md)
                continue
            parsed = _parse_skill_md(content)
            if not parsed:
                _logger.warning("Invalid frontmatter in %s", skill_md)
                continue
            frontmatter, _ = parsed
            name = frontmatter.get("name")
            description = frontmatter.get("description")
            if not name or not description:
                _logger.warning("Missing name or description in %s", skill_md)
                continue
            if name in self._skills:
                continue
            self._skills[name] = SkillMeta(
                name=name,
                description=description,
                path=skill_dir,
                location=location,
            )

    def get(self, name: str) -> SkillMeta | None:
        return self._skills.get(name)

    def load_body(self, name: str) -> str | None:
        meta = self._skills.get(name)
        if not meta:
            return None
        try:
            content = (meta.path / "SKILL.md").read_text()
        except OSError:
            return None
        parsed = _parse_skill_md(content)
        if not parsed:
            return None
        _, body = parsed
        return body.strip()

    def to_prompt_xml(self) -> str:
        if not self._skills:
            return ""
        lines = ["<available_skills>"]
        for meta in self._skills.values():
            lines.append("  <skill>")
            lines.append(f"    <name>{meta.name}</name>")
            lines.append(f"    <description>{meta.description}</description>")
            lines.append(f"    <location>{meta.location}</location>")
            lines.append("  </skill>")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def remove(self, name: str) -> bool:
        meta = self._skills.get(name)
        if not meta:
            return False
        import shutil

        shutil.rmtree(meta.path, ignore_errors=True)
        del self._skills[name]
        _logger.info("Removed skill '%s'", name)
        return True

    def reload(self, dirs: list[tuple[Path, str]]) -> None:
        self._skills.clear()
        self.load(dirs)

    @property
    def names(self) -> list[str]:
        return list(self._skills)

    def __len__(self) -> int:
        return len(self._skills)

    def __bool__(self) -> bool:
        return bool(self._skills)
