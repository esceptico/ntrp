from ntrp.memory.models import Fact, FactContext


def format_facts_list(facts: list[str]) -> str:
    return "\n".join(f"- {f}" for f in facts)


def format_memory_context(user_facts: list[Fact], recent_facts: list[Fact]) -> str:
    if not user_facts and not recent_facts:
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

    return "\n".join(lines)


def format_context(context: FactContext) -> str:
    if not context.facts and not context.observations:
        return ""

    lines = ["## Memory"]

    if context.observations:
        lines.append("\n### Patterns")
        lines.extend(f"- {obs.summary}" for obs in context.observations)

    if context.facts:
        lines.append("\n### Facts")
        lines.extend(f"- {fact.text}" for fact in context.facts)

    return "\n".join(lines)
