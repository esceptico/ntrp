from ntrp.memory.models import Fact, Observation

MEMORY_CONTEXT_CHAR_BUDGET = 3000


def format_memory_context(
    user_facts: list[Fact] | None = None,
    recent_facts: list[Fact] | None = None,
    query_facts: list[Fact] | None = None,
    query_observations: list[Observation] | None = None,
) -> str:
    if not user_facts and not recent_facts and not query_facts and not query_observations:
        return ""

    lines: list[str] = []

    # Priority order: user context > query-conditioned > recent > observations

    sections: list[tuple[str, list[str]]] = []
    if user_facts:
        sections.append(("**About user**", [f"- {f.text}" for f in user_facts]))
    if query_facts:
        sections.append(("**Relevant**", [f"- {f.text}" for f in query_facts]))
    if recent_facts:
        sections.append(("**Recent**", [f"- {f.text}" for f in recent_facts]))
    if query_observations:
        sections.append(("**Patterns**", [f"- {obs.summary}" for obs in query_observations]))

    budget = MEMORY_CONTEXT_CHAR_BUDGET
    for header, items in sections:
        section_lines = [header] + items
        section_text = "\n".join(section_lines)
        if budget - len(section_text) < 0:
            # Fit as many items as possible
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
