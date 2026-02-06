from ntrp.memory.models import Fact, Observation


def format_memory_context(
    user_facts: list[Fact] | None = None,
    recent_facts: list[Fact] | None = None,
    query_facts: list[Fact] | None = None,
    query_observations: list[Observation] | None = None,
) -> str:
    if not user_facts and not recent_facts and not query_facts and not query_observations:
        return ""

    lines = []

    if user_facts:
        lines.append("**About user**")
        lines.extend(f"- {f.text}" for f in user_facts)

    if recent_facts:
        if lines:
            lines.append("")
        lines.append("**Recent**")
        lines.extend(f"- {f.text}" for f in recent_facts)

    if query_facts:
        if lines:
            lines.append("")
        lines.append("**Relevant**")
        lines.extend(f"- {f.text}" for f in query_facts)

    if query_observations:
        if lines:
            lines.append("")
        lines.append("**Patterns**")
        lines.extend(f"- {obs.summary}" for obs in query_observations)

    return "\n".join(lines)
