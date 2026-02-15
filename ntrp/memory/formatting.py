from ntrp.memory.models import Fact, Observation

MEMORY_CONTEXT_CHAR_BUDGET = 3000


def _format_observation(obs: Observation) -> str:
    line = f"- {obs.summary}"
    if obs.history:
        for entry in obs.history[-2:]:
            month = entry.changed_at.strftime("%b %Y")
            line += f' (previously: "{entry.previous_text}", changed {month})'
    return line


def _format_sections(
    sections: list[tuple[str, list[str]]],
    budget: int = MEMORY_CONTEXT_CHAR_BUDGET,
) -> str:
    lines: list[str] = []
    for header, items in sections:
        section_lines = [header] + items
        section_text = "\n".join(section_lines)
        if budget - len(section_text) < 0:
            if lines:
                lines.append("")
            lines.append(header)
            for item in items:
                if budget - len(item) < 0:
                    break
                lines.append(item)
                budget -= len(item) + 1
            break
        if lines:
            lines.append("")
        lines.extend(section_lines)
        budget -= len(section_text) + 1
    return "\n".join(lines)


def format_session_memory(user_facts: list[Fact] | None = None) -> str:
    """Format stable user memory for the system prompt (cacheable)."""
    if not user_facts:
        return ""
    sections = [("**About user**", [f"- {f.text}" for f in user_facts])]
    return _format_sections(sections)


def format_memory_context(
    query_facts: list[Fact] | None = None,
    query_observations: list[Observation] | None = None,
) -> str:
    """Format full memory context (used by recall tool)."""
    if not query_facts and not query_observations:
        return ""

    sections: list[tuple[str, list[str]]] = []
    if query_facts:
        sections.append(("**Relevant**", [f"- {f.text}" for f in query_facts]))
    if query_observations:
        sections.append(("**Patterns**", [_format_observation(obs) for obs in query_observations]))

    return _format_sections(sections)
