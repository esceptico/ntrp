import re

from ntrp.memory.pages import Page

_LOOP_HEADING = re.compile(r"^##\s+open loops\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_PROVENANCE = re.compile(r"\s*\((?:from chat|record:[^)]*)\)\.?\s*$")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def parse_open_loops(prose: str) -> list[str]:
    loops: list[str] = []
    in_section = False
    for line in prose.splitlines():
        stripped = line.strip()
        if _LOOP_HEADING.match(stripped):
            in_section = True
            continue
        if in_section and _HEADING.match(stripped):
            break
        if in_section:
            m = _BULLET.match(stripped)
            if m:
                text = _MD_BOLD.sub(r"\1", m.group(1))
                loops.append(_PROVENANCE.sub("", text).strip())
    return loops


def page_summary(page: Page) -> dict:
    return {
        "title": page.frontmatter.get("title", ""),
        "updated": str(page.frontmatter.get("updated", "")),
        "open_loops": parse_open_loops(page.prose),
    }


def slice_automation_match(name: str, key: str) -> bool:
    """Match an automation name against a slice key.

    Seeded slice automations are named exactly `slice:{key}` (see
    _seed_slice_automations); colon-suffixed names like `slice:{key}:daily`
    are reserved for future sub-automations.
    """
    base = f"slice:{key}"
    return name == base or name.startswith(f"{base}:")
