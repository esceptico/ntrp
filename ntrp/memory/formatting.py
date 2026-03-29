from ntrp.memory.models import Fact, Observation, SourceType

MEMORY_CONTEXT_CHAR_BUDGET = 3000


def _source_label(fact: Fact) -> str:
    date = fact.happened_at or fact.created_at
    date_str = date.strftime("%b %d") if date else ""
    if fact.source_type == SourceType.CHAT:
        return f" (conversation, {date_str})" if date_str else " (conversation)"
    if fact.source_type and date_str:
        return f" ({fact.source_type}, {date_str})"
    if date_str:
        return f" ({date_str})"
    return ""


def _format_bundled_observation(obs: Observation, source_facts: list[Fact]) -> str:
    lines = [f"- {obs.summary} ({obs.evidence_count} sources)"]
    for fact in source_facts[:5]:
        lines.append(f"  - {fact.text}{_source_label(fact)}")
    return "\n".join(lines)


def _format_observation(obs: Observation) -> str:
    return f"- {obs.summary}"


def _format_sections(
    sections: list[tuple[str, list[str]]],
    budget: int = MEMORY_CONTEXT_CHAR_BUDGET,
) -> str:
    lines: list[str] = []
    for header, items in sections:
        section_lines = [header] + items
        section_text = "\n".join(section_lines)
        if budget - len(section_text) < 0:
            # Section doesn't fit whole — add items individually
            budget -= len(header) + 1
            added = []
            for item in items:
                if budget - len(item) - 1 < 0:
                    break
                added.append(item)
                budget -= len(item) + 1
            if added:
                if lines:
                    lines.append("")
                lines.append(header)
                lines.extend(added)
            continue
        if lines:
            lines.append("")
        lines.extend(section_lines)
        budget -= len(section_text) + 1
    return "\n".join(lines)


def format_session_memory(
    observations: list[Observation] | None = None,
    user_facts: list[Fact] | None = None,
) -> str | None:
    """Format stable user memory for the system prompt (cacheable)."""
    if not observations and not user_facts:
        return None
    sections: list[tuple[str, list[str]]] = []
    if observations:
        sections.append(("**Patterns**", [_format_observation(obs) for obs in observations]))
    if user_facts:
        sections.append(("**About user**", [f"- {f.text}" for f in user_facts]))
    return _format_sections(sections)


def format_memory_context(
    query_facts: list[Fact] | None = None,
    query_observations: list[Observation] | None = None,
    bundled_sources: dict[int, list[Fact]] | None = None,
) -> str | None:
    """Format full memory context (used by recall tool).

    Observations are primary, with source facts bundled as evidence.
    Standalone facts fill gaps for unconsolidated content.
    """
    if not query_facts and not query_observations:
        return None

    sections: list[tuple[str, list[str]]] = []

    if query_observations:
        obs_items = []
        for obs in query_observations:
            sources = (bundled_sources or {}).get(obs.id, [])
            if sources:
                obs_items.append(_format_bundled_observation(obs, sources))
            else:
                obs_items.append(_format_observation(obs))
        sections.append(("**Patterns**", obs_items))

    if query_facts:
        sections.append(("**Relevant**", [f"- {f.text}{_source_label(f)}" for f in query_facts]))

    return _format_sections(sections)
