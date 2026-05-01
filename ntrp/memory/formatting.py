from dataclasses import dataclass, field

from ntrp.memory.models import Fact, FactContext, FactKind, Observation, SourceType

MEMORY_CONTEXT_CHAR_BUDGET = 3000

PROFILE_SECTIONS = (
    (FactKind.IDENTITY, "**Identity**"),
    (FactKind.PREFERENCE, "**Preferences**"),
    (FactKind.RELATIONSHIP, "**Relationships**"),
    (FactKind.CONSTRAINT, "**Standing constraints**"),
)


@dataclass(frozen=True)
class MemoryContextRender:
    text: str
    fact_ids: list[int] = field(default_factory=list)
    observation_ids: list[int] = field(default_factory=list)
    bundled_fact_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class _TrackedItem:
    text: str
    fact_ids: tuple[int, ...] = ()
    observation_ids: tuple[int, ...] = ()
    bundled_fact_ids: tuple[int, ...] = ()
    allow_clip: bool = False


def model_memory_context(context: FactContext) -> FactContext:
    if not context.observations:
        return context
    return context.model_copy(update={"facts": []})


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


def _tracked_bundled_observation(obs: Observation, source_facts: list[Fact]) -> list[_TrackedItem]:
    items = [
        _TrackedItem(
            text=f"- {obs.summary} ({obs.evidence_count} sources)",
            observation_ids=(obs.id,),
            allow_clip=True,
        )
    ]
    items.extend(
        _TrackedItem(
            text=f"  - {fact.text}{_source_label(fact)}",
            fact_ids=(fact.id,),
            bundled_fact_ids=(fact.id,),
        )
        for fact in source_facts[:5]
    )
    return items


def _format_observation(obs: Observation) -> str:
    return f"- {obs.summary}"


def _profile_sections(profile_facts: list[Fact]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for kind, header in PROFILE_SECTIONS:
        items = [f"- {fact.text}" for fact in profile_facts if fact.kind == kind]
        if items:
            sections.append((header, items))
    return sections


def _dedupe(ids: list[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def _clip_text(text: str, budget: int) -> str | None:
    if budget <= 0:
        return None
    if len(text) <= budget:
        return text
    if budget <= 3:
        return "." * budget
    return text[: budget - 3].rstrip() + "..."


def _clip_item(item: _TrackedItem, budget: int) -> _TrackedItem | None:
    if not item.allow_clip and len(item.text) > budget:
        return None
    text = _clip_text(item.text, budget)
    if text is None:
        return None
    return _TrackedItem(
        text=text,
        fact_ids=item.fact_ids,
        observation_ids=item.observation_ids,
        bundled_fact_ids=item.bundled_fact_ids,
        allow_clip=item.allow_clip,
    )


def _collect_render(lines: list[str], items: list[_TrackedItem]) -> MemoryContextRender | None:
    text = "\n".join(lines)
    if not text:
        return None
    return MemoryContextRender(
        text=text,
        fact_ids=_dedupe([fact_id for item in items for fact_id in item.fact_ids]),
        observation_ids=_dedupe([obs_id for item in items for obs_id in item.observation_ids]),
        bundled_fact_ids=_dedupe([fact_id for item in items for fact_id in item.bundled_fact_ids]),
    )


def _format_tracked_sections(
    sections: list[tuple[str, list[_TrackedItem]]],
    budget: int = MEMORY_CONTEXT_CHAR_BUDGET,
) -> MemoryContextRender | None:
    lines: list[str] = []
    included: list[_TrackedItem] = []
    for header, items in sections:
        section_lines = [header] + [item.text for item in items]
        section_text = "\n".join(section_lines)
        if budget - len(section_text) < 0:
            budget -= len(header) + 1
            added: list[_TrackedItem] = []
            for item in items:
                item_budget = budget - 1
                if item_budget < 1:
                    break
                fitted = _clip_item(item, item_budget)
                if fitted is None:
                    break
                added.append(fitted)
                budget -= len(fitted.text) + 1
                if fitted.text != item.text:
                    break
            if added:
                if lines:
                    lines.append("")
                lines.append(header)
                lines.extend(item.text for item in added)
                included.extend(added)
            continue
        if lines:
            lines.append("")
        lines.extend(section_lines)
        included.extend(items)
        budget -= len(section_text) + 1
    return _collect_render(lines, included)


def _format_sections(
    sections: list[tuple[str, list[str]]],
    budget: int = MEMORY_CONTEXT_CHAR_BUDGET,
) -> str:
    tracked = [(header, [_TrackedItem(text=item) for item in items]) for header, items in sections]
    render = _format_tracked_sections(tracked, budget=budget)
    return render.text if render else ""


def format_session_memory(
    profile_facts: list[Fact] | None = None,
    observations: list[Observation] | None = None,
    user_facts: list[Fact] | None = None,
) -> str | None:
    """Format stable user memory for the system prompt (cacheable)."""
    if not profile_facts and not observations and not user_facts:
        return None
    sections: list[tuple[str, list[str]]] = []
    if observations:
        sections.append(("**Patterns**", [_format_observation(obs) for obs in observations]))
    if profile_facts:
        sections.extend(_profile_sections(profile_facts))
    if user_facts:
        sections.append(("**About user**", [f"- {f.text}" for f in user_facts]))
    return _format_sections(sections)


def format_session_memory_render(
    profile_facts: list[Fact] | None = None,
    observations: list[Observation] | None = None,
    user_facts: list[Fact] | None = None,
) -> MemoryContextRender | None:
    if not profile_facts and not observations and not user_facts:
        return None
    sections: list[tuple[str, list[_TrackedItem]]] = []
    if observations:
        sections.append((
            "**Patterns**",
            [_TrackedItem(text=_format_observation(obs), observation_ids=(obs.id,)) for obs in observations],
        ))
    if profile_facts:
        for kind, header in PROFILE_SECTIONS:
            items = [
                _TrackedItem(text=f"- {fact.text}", fact_ids=(fact.id,))
                for fact in profile_facts
                if fact.kind == kind
            ]
            if items:
                sections.append((header, items))
    if user_facts:
        sections.append((
            "**About user**",
            [_TrackedItem(text=f"- {fact.text}", fact_ids=(fact.id,)) for fact in user_facts],
        ))
    return _format_tracked_sections(sections)


def format_memory_context(
    query_facts: list[Fact] | None = None,
    query_observations: list[Observation] | None = None,
    bundled_sources: dict[int, list[Fact]] | None = None,
    budget: int = MEMORY_CONTEXT_CHAR_BUDGET,
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

    return _format_sections(sections, budget=budget)


def format_memory_context_render(
    query_facts: list[Fact] | None = None,
    query_observations: list[Observation] | None = None,
    bundled_sources: dict[int, list[Fact]] | None = None,
    budget: int = MEMORY_CONTEXT_CHAR_BUDGET,
) -> MemoryContextRender | None:
    if not query_facts and not query_observations:
        return None

    sections: list[tuple[str, list[_TrackedItem]]] = []

    if query_observations:
        obs_items: list[_TrackedItem] = []
        for obs in query_observations:
            sources = (bundled_sources or {}).get(obs.id, [])
            if sources:
                obs_items.extend(_tracked_bundled_observation(obs, sources))
            else:
                obs_items.append(_TrackedItem(text=_format_observation(obs), observation_ids=(obs.id,), allow_clip=True))
        sections.append(("**Patterns**", obs_items))

    if query_facts:
        sections.append((
            "**Relevant**",
            [
                _TrackedItem(text=f"- {fact.text}{_source_label(fact)}", fact_ids=(fact.id,))
                for fact in query_facts
            ],
        ))

    return _format_tracked_sections(sections, budget=budget)
